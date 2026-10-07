import json
import logging
import time
import secrets
from datetime import datetime, timezone

import discord

from .common import block_summary


EMBED_COLORS = (0x8B5CF6, 0x5865F2, 0x00A8DD, 0x00B894, 0xD9A520, 0xF2994A, 0xE64964, 0xD65DB1)


def status_embed(controller, project, event, payload):
    """One compact text hierarchy: vertical indentation, not a grid of fields."""
    def plain(value, limit=300):
        return discord.utils.escape_mentions(discord.utils.escape_markdown(
            controller.redactor.clean(str(value)).replace('\n', ' ')[:limit]))

    def code(value):
        return '`' + controller.redactor.clean(str(value or '—')).replace('`', 'ˋ').replace('\n', ' ')[:180] + '`'

    kind = event['kind']
    reason = payload.get('reason') or project.get('block_reason') or {}
    if isinstance(reason, str):
        try:
            reason = json.loads(reason)
        except json.JSONDecodeError:
            reason = {'reason': reason}
    if not isinstance(reason, dict):
        reason = {}
    offline = kind == 'stalled' and reason.get('reason') == 'Windows offline'
    titles = {'active': 'Project Status', 'paused': 'Project Paused', 'stalled': 'Project Stalled',
              'usage limited': 'Usage Limited', 'limited by budget': 'Budget Limited',
              'complete': 'Project Complete', 'critical': 'Infrastructure Alert'}
    title = 'Windows Worker Offline' if offline else titles.get(kind, 'Project Status')
    label = {'active': 'Running', 'paused': 'Paused', 'stalled': 'Attention required',
             'usage limited': 'Waiting for reset', 'limited by budget': 'Budget reached',
             'complete': 'Finished', 'critical': 'Attention required'}.get(kind, 'Updated')
    status = kind if kind in titles and kind != 'critical' else project['goal_status']
    summary = block_summary(project, reason, status)
    sections = []
    if summary:
        sections.append('**' + ('Reasons' if len(summary['reasons']) > 1 else 'Reason') + '**\n' +
                        '\n'.join(f'{i}. {plain(text, 140)}' for i, text in enumerate(summary['reasons'], 1)))
        sections.append('**Erklärung**\n' + plain(summary['explanation'], 320))
        sections.append('**Lösung**\n' + '\n'.join(
            f'{i}. {plain(text, 240)}' for i, text in enumerate(summary['solution'], 1)))
        if summary['requires_user']:
            sections[-1] += '\nKein automatisches Resume ohne Nutzerfreigabe.'
    if offline:
        heartbeat = controller.db.setting('windows_last_heartbeat')
        last_seen = f'<t:{int(heartbeat)}:F> (<t:{int(heartbeat)}:R>)' if heartbeat else '`unavailable`'
        sections.append('**Windows Worker**\n- ' + ('Online' if getattr(controller, 'windows_online', False) else 'Offline') + '\n'
            '│ Last heartbeat: ' + last_seen + '\n'
            '│ Required: **yes**\n│ Auto resume: **' + ('enabled' if reason.get('requires_user') is False else 'disabled') + '**')
    lines = ['**Project**', '- ' + label, '│ Name: ' + code(project['display_name']),
             '│ Status: **' + plain(status) + '**']
    if kind == 'complete':
        lines += ['│ Final Commit: ' + code(payload.get('commit') or project['last_commit']),
                  '│ CI: **' + plain(payload.get('ci') or project['last_ci_status'] or 'unknown') + '**']
    elif kind == 'usage limited':
        tracked = next((s for s in controller.unsnooze.get('sessions', [])
                        if s.get('sessionId') == project['codex_session_id']), {})
        reset = (payload.get('usage_limit') or json.loads(project.get('usage_limit') or '{}')).get('resetAt') or tracked.get('resetAt')
        lines.append('│ Reset: ' + (f'<t:{int(reset / 1000)}:F>' if reset else '`unknown`'))
    if kind != 'complete':
        lines.append('│ Session: ' + code(project['codex_session_id']))
    lines.append('│ Repo: ' + code(project['github_repo']))
    sections.append('\n'.join(lines))
    if summary and summary['details']:
        sections.append('**Technische Details**\nDashboard → Projekt → Details; der vollständige Blocker bleibt dort erhalten.')
    elif payload.get('message'):
        sections.append('**Details**\n│ ' + plain(payload['message'], 650))
    if kind == 'usage limited':
        prompt_limit = controller.db.setting('prompt_limit/' + project['project_id'])
        policy = 'New prompt required after reset; failed prompt is not replayed' if prompt_limit else 'Unsnooze'
        sections.append('**Resume**\n- Scheduler-controlled\n│ Policy: ' + code(policy) + '\n│ Queue position: ' +
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
        from .lifecycle import finish, record_error
        async with controller.lock:
            project = controller.db.get(project['project_id'])
            if project['lifecycle'] != 'ready' or project['operation']:
                return
            controller.db.update(project['project_id'], operation=json.dumps({'kind': 'close-channel'}))
            try:
                await finish(controller, controller.db.get(project['project_id']))
            except Exception as exc:
                record_error(controller, project['project_id'], exc)


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
            """SELECT * FROM events WHERE sent_at IS NULL OR (kind='usage limited'
               AND json_extract(payload,'$.usage_limit.resetAt') IS NOT NULL
               AND json_extract(payload,'$.reset_notified') IS NULL)
               ORDER BY event_id LIMIT 10""").fetchall()
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
            found = None
            # No local-time cutoff: Pi/Discord clock skew must not defeat crash deduplication.
            async for old in channel.history(limit=None):
                if old.author.id == self.user.id and (old.content.endswith(marker) or any(
                        embed.footer.text == f'CodexPi • Event {event["event_id"]}' for embed in old.embeds)):
                    found = old
                    break
            if not found and event['sent_at'] is None:
                await channel.send(embed=status_embed(self.controller, project, event, payload),
                                   view=CloseView(self) if event['kind'] == 'complete' else None)
            elif found and payload.get('usage_limit') and not payload.get('reset_notified'):
                await found.edit(embed=status_embed(self.controller, project, event, payload))
            if payload.get('usage_limit'):
                payload['reset_notified'] = True
            self.controller.db.conn.execute('UPDATE events SET sent_at=? WHERE event_id=?',
                                           (time.time(), event['event_id']))
            self.controller.db.conn.execute('UPDATE events SET payload=? WHERE event_id=?',
                                           (json.dumps(payload), event['event_id']))
