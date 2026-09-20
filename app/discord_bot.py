import json
import logging
import time
import secrets
from datetime import datetime, timezone

import discord


EMBED_COLORS = (0x8B5CF6, 0x5865F2, 0x00A8DD, 0x00B894, 0xD9A520, 0xF2994A, 0xE64964, 0xD65DB1)


def status_embed(controller, project, event, payload):
    """One compact text hierarchy: vertical indentation, not a grid of fields."""
    def plain(value, limit=300):
        return discord.utils.escape_mentions(discord.utils.escape_markdown(
            controller.redactor.clean(str(value)).replace('\n', ' ')[:limit]))

    def code(value):
        return '`' + controller.redactor.clean(str(value or '—')).replace('`', 'ˋ').replace('\n', ' ')[:180] + '`'

    kind = event['kind']
    reason = payload.get('reason') or {}
    if isinstance(reason, str):
        try:
            reason = json.loads(reason)
        except json.JSONDecodeError:
            reason = {'reason': reason}
    offline = kind == 'stalled' and reason.get('reason') == 'Windows offline'
    titles = {'active': 'Project Status', 'paused': 'Project Paused', 'stalled': 'Project Stalled',
              'usage limited': 'Usage Limited', 'limited by budget': 'Budget Limited',
              'complete': 'Project Complete', 'critical': 'Infrastructure Alert'}
    title = 'Windows Worker Offline' if offline else titles.get(kind, 'Project Status')
    label = {'active': 'Running', 'paused': 'Paused', 'stalled': 'Attention required',
             'usage limited': 'Waiting for reset', 'limited by budget': 'Budget reached',
             'complete': 'Finished', 'critical': 'Attention required'}.get(kind, 'Updated')
    status = kind if kind in titles and kind != 'critical' else project['goal_status']
    sections = []
    if offline:
        age = max(0, int(time.monotonic() - controller.worker_seen)) if controller.worker_seen else None
        sections.append('**Windows Worker**\n- Offline\n'
            '│ Last heartbeat: ' + code(str(age) + 's ago' if age is not None else 'unavailable') + '\n'
            '│ Required: **yes**\n│ Auto resume: **' + ('enabled' if reason.get('requires_user') is False else 'disabled') + '**')
    lines = ['**Project**', '- ' + label, '│ Name: ' + code(project['display_name']),
             '│ Status: **' + plain(status) + '**']
    if kind == 'complete':
        lines += ['│ Final Commit: ' + code(payload.get('commit') or project['last_commit']),
                  '│ CI: **' + plain(payload.get('ci') or project['last_ci_status'] or 'unknown') + '**']
    elif kind == 'usage limited':
        tracked = next((s for s in controller.unsnooze.get('sessions', [])
                        if s.get('sessionId') == project['codex_session_id']), {})
        reset = tracked.get('resetAt')
        lines.append('│ Reset: ' + (f'<t:{int(reset / 1000)}:F>' if reset else '`unknown`'))
    if kind != 'complete':
        lines.append('│ Session: ' + code(project['codex_session_id']))
    lines.append('│ Repo: ' + code(project['github_repo']))
    if reason.get('reason'):
        lines.append('│ Block Reason: ' + plain(reason['reason']))
    sections.append('\n'.join(lines))
    if reason.get('details'):
        sections.append('**Required**\n- ' + ('User action' if reason.get('requires_user') else 'Dependency') +
                        '\n│ Detail: ' + plain(reason['details'], 650))
    elif payload.get('message'):
        sections.append('**Details**\n│ ' + plain(payload['message'], 650))
    if kind == 'usage limited':
        sections.append('**Resume**\n- Scheduler-controlled\n│ Policy: `Unsnooze`\n│ Queue position: ' +
                        code(project['queue_position']))
    if kind in ('active', 'complete'):
        waiting = [p for p in controller.db.all() if p['project_id'] != project['project_id']
                   and p['queue_position'] is not None and p['goal_status'] == 'paused']
        sections.append('**Queue**\n- ' + str(len(waiting)) + ' waiting\n│ Next: ' +
                        code(waiting[0]['display_name'] if waiting else 'none'))
    embed = discord.Embed(title='CodexPi — ' + title, description='\n\n'.join(sections),
                          color=payload['embed_color'], timestamp=datetime.fromtimestamp(event['created_at'], timezone.utc))
    embed.set_footer(text=f'CodexPi • Event {event["event_id"]}')
    if project['github_repo']:
        embed.url = 'https://github.com/' + project['github_repo']
    return embed


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
            embed = discord.Embed(title='CodexPi — Action unavailable', color=secrets.choice(EMBED_COLORS),
                description='**Close**\n- Permission required\n│ Project must be **complete**.\n│ Member needs **Manage Channels**.',
                timestamp=discord.utils.utcnow())
            embed.set_footer(text='CodexPi')
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
                and permissions.read_message_history and permissions.embed_links):
            raise RuntimeError('Bot requires View Channel, Send Messages, Embed Links, Manage Channels and Read Message History in the category')
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
            if 'embed_color' not in payload:
                payload['embed_color'] = secrets.choice(EMBED_COLORS)
                self.controller.db.conn.execute('UPDATE events SET payload=? WHERE event_id=?',
                                               (json.dumps(payload), event['event_id']))
            # Stable footer lets crash recovery recognize a message sent before its DB ACK.
            marker = f'CodexPi event {event["event_id"]}'
            found = False
            async for old in channel.history(limit=50):
                if old.author.id == self.user.id and (old.content.endswith(marker) or any(
                        embed.footer.text == f'CodexPi • Event {event["event_id"]}' for embed in old.embeds)):
                    found = True
                    break
            if not found:
                await channel.send(embed=status_embed(self.controller, project, event, payload),
                                   view=CloseView(self) if event['kind'] == 'complete' else None)
            self.controller.db.conn.execute('UPDATE events SET sent_at=? WHERE event_id=?',
                                           (time.time(), event['event_id']))
