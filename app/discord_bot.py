import json
import logging
import time

import discord


class CloseView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Close', style=discord.ButtonStyle.danger, custom_id='codexpi:close')
    async def close_project_channel(self, interaction, button):
        controller = self.bot.controller
        project = next((p for p in controller.db.all()
                        if p['discord_channel_id'] == str(interaction.channel_id)), None)
        if (not project or project['goal_status'] != 'complete' or not interaction.guild or
                not interaction.user.guild_permissions.manage_channels):
            await interaction.response.send_message('Only a server member with Manage Channels can close a completed project.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        controller.db.update(project['project_id'], operation=json.dumps({'kind': 'close-channel'}))
        await interaction.channel.delete(reason='CodexPi completed project closed by user')
        controller.db.update(project['project_id'], discord_channel_id=None, operation=None)


class Bot(discord.Client):
    def __init__(self, controller):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.controller = controller

    async def setup_hook(self):
        self.add_view(CloseView(self))

    async def on_ready(self):
        logging.getLogger('discord').info('Bot connected')

    async def category(self):
        category = self.get_channel(int(self.controller.config['discord_category']))
        if category is None:
            category = await self.fetch_channel(int(self.controller.config['discord_category']))
        if not isinstance(category, discord.CategoryChannel):
            raise RuntimeError('Configured Discord category is not a category')
        permissions = category.permissions_for(category.guild.me)
        if not (permissions.view_channel and permissions.send_messages and permissions.manage_channels
                and permissions.read_message_history):
            raise RuntimeError('Bot requires View Channel, Send Messages, Manage Channels and Read Message History in the category')
        return category

    async def ensure_channel(self, project):
        category = await self.category()
        marker = 'CodexPi project ' + project['project_id']
        if project.get('discord_channel_id'):
            try:
                channel = await self.fetch_channel(int(project['discord_channel_id']))
                if channel.category_id != category.id or channel.topic != marker:
                    raise RuntimeError('Discord channel identity mismatch')
                return channel
            except discord.NotFound:
                pass
        channels = await category.guild.fetch_channels()
        for channel in channels:
            if isinstance(channel, discord.TextChannel) and channel.category_id == category.id:
                if channel.topic == marker:
                    return channel
                if channel.name == project['slug']:
                    raise RuntimeError('Discord channel name already exists without matching ownership')
        return await category.create_text_channel(project['slug'], topic=marker,
                                                  reason='CodexPi private project creation')

    async def send_pending(self):
        pending = self.controller.db.conn.execute(
            'SELECT * FROM events WHERE sent_at IS NULL ORDER BY event_id LIMIT 10').fetchall()
        for event in pending:
            project = self.controller.db.get(event['project_id'])
            if not project['discord_channel_id']:
                continue
            channel = await self.fetch_channel(int(project['discord_channel_id']))
            payload = json.loads(event['payload'])
            text = f"Project {event['kind']} — {project['display_name']}\n"
            if event['kind'] == 'complete':
                text += f"Repository: https://github.com/{payload['repo']}\nFinal commit: {payload['commit']}\nCI: {payload['ci']}"
            elif payload.get('reason'):
                reason = json.loads(payload['reason']) if isinstance(payload['reason'], str) else payload['reason']
                text += f"Reason: {reason.get('reason', '')}\nRequired: {reason.get('details', '')}"
            else:
                text += payload.get('message', 'Status changed')
            # Stable footer lets crash recovery recognize a message sent before its DB ACK.
            marker = f'CodexPi event {event["event_id"]}'
            found = False
            async for old in channel.history(limit=50):
                if old.author.id == self.user.id and old.content.endswith(marker):
                    found = True
                    break
            if not found:
                await channel.send(self.controller.redactor.clean(text)[:1800] + '\n' + marker,
                                   view=CloseView(self) if event['kind'] == 'complete' else None)
            self.controller.db.conn.execute('UPDATE events SET sent_at=? WHERE event_id=?',
                                           (time.time(), event['event_id']))
