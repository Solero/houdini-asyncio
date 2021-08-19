import datetime

from houdini import handlers
from houdini.constants import ClientType
from houdini.data import db
from houdini.data.moderator import Ban, Report, Warning
from houdini.data.penguin import Penguin
from houdini.handlers import XTPacket


@handlers.handler(XTPacket('o', 'k'))
async def handle_kick_player(p, penguin_id: int):
    if p.moderator:
        await moderator_kick(p, penguin_id)


@handlers.handler(XTPacket('o', 'b'), client=ClientType.Legacy)
async def handle_ban_player(p, penguin_id: int, message: str):
    if p.moderator:
        await moderator_ban(p, penguin_id, comment=message)


@handlers.handler(XTPacket('o', 'm'))
async def handle_mute_player(p, penguin_id: int):
    if p.moderator:
        if penguin_id in p.server.penguins_by_id:
            player = p.server.penguins_by_id[penguin_id]
            if not player.moderator:
                player.muted = True


@handlers.handler(XTPacket('o', 'initban'), client=ClientType.Vanilla)
@handlers.player_attribute(moderator=True)
async def handle_init_ban(p, penguin_id: int, message: str):
    player = p.server.penguins_by_id[penguin_id] if penguin_id in p.server.penguins_by_id \
        else await Penguin.get(penguin_id)
    if not player.moderator:
        number_bans = await db.select([db.func.count(Ban.penguin_id)]).where(
            Ban.penguin_id == player.id).gino.scalar()

        await p.send_xt('initban', penguin_id, 0, number_bans, message, player.username)


@handlers.handler(XTPacket('o', 'ban'), client=ClientType.Vanilla)
@handlers.player_attribute(moderator=True)
async def handle_moderator_ban(p, penguin_id: int, ban_type: int, reason: int, duration: int, message: str, notes: str):
    player = p.server.penguins_by_id[penguin_id] if penguin_id in p.server.penguins_by_id \
        else await Penguin.get(penguin_id)
    if not player.moderator:
        date_issued = datetime.datetime.now()
        date_expires = date_issued + datetime.timedelta(hours=duration)

        if duration == 0:
            await player.update(permaban=True).apply()

        await Ban.create(penguin_id=player.id, issued=date_issued, expires=date_expires,
                         moderator_id=p.id, reason=reason, comment=notes, message=message)

        if penguin_id in p.server.penguins_by_id:
            if player.is_vanilla_client:
                await player.send_xt('ban', ban_type, reason, duration, notes)
            else:
                await player.send_error(610, message)
            await player.close()


@handlers.handler(XTPacket('m', 'r'))
async def handle_report(p, penguin_id: int, reason: int = 0):
    date_now = datetime.datetime.now()
    await Report.create(penguin_id=penguin_id, reporter_id=p.id, report_type=reason,
                        date=date_now, server_id=p.server.config.id, room_id=p.room.id)


@handlers.handler(XTPacket('o', 'moderatormessage'), client=ClientType.Vanilla)
@handlers.player_attribute(moderator=True)
async def handle_moderator_message(p, warning_type: int, penguin_id: int):
    player = p.server.penguins_by_id[penguin_id] if penguin_id in p.server.penguins_by_id \
        else await Penguin.get(penguin_id)
    date_issued = datetime.datetime.now()
    date_expires = date_issued + datetime.timedelta(hours=48)
    warning_count = await db.select([db.func.count(Warning.expires)]).where(
        (Warning.penguin_id == player.id) & (Warning.expires >= date_issued)).gino.scalar()

    if warning_count >= 3:
        return await moderator_ban(p, player.id, message='Exceeded warning limit')

    await player.send_xt('moderatormessage', warning_type)
    await Warning.create(penguin_id=player.id, issued=date_issued, expires=date_expires)


async def cheat_kick(p, penguin_id):
    if penguin_id in p.server.penguins_by_id:
        await p.server.penguins_by_id[penguin_id].send_error_and_disconnect(800)


async def cheat_ban(p, penguin_id, hours=24, comment=''):
    if penguin_id in p.server.penguins_by_id:
        player = p.server.penguins_by_id[penguin_id]

        number_bans = await db.select([db.func.count(Ban.penguin_id)]).where(
            Ban.penguin_id == player.id).gino.scalar()

        date_issued = datetime.datetime.now()
        date_expires = date_issued + datetime.timedelta(hours=hours)

        if number_bans >= 3:
            await player.update(permaban=True).apply()

        await Ban.create(penguin_id=player.id, issued=date_issued, expires=date_expires,
                         moderator_id=p.id, reason=1, comment=comment, message='Cheat ban')

        if penguin_id in p.server.penguins_by_id:
            await player.send_error_and_disconnect(611, comment)


async def moderator_kick(p, penguin_id):
    if penguin_id in p.server.penguins_by_id:
        player = p.server.penguins_by_id[penguin_id]
        if not player.moderator:
            for penguin in p.server.penguins_by_id.values():
                if penguin.moderator:
                    await penguin.send_xt('ma', 'k', penguin_id, player.username)
            await player.send_error_and_disconnect(5)


async def moderator_ban(p, penguin_id, hours=24, comment='', message=''):
    player = p.server.penguins_by_id[penguin_id] if penguin_id in p.server.penguins_by_id \
        else await Penguin.get(penguin_id)
    if not player.moderator:
        for penguin in p.server.penguins_by_id.values():
            if penguin.moderator:
                await penguin.send_xt('ma', 'b', penguin_id, player.username)

        number_bans = await db.select([db.func.count(Ban.penguin_id)]).where(
            Ban.penguin_id == player.id).gino.scalar()

        date_issued = datetime.datetime.now()
        date_expires = date_issued + datetime.timedelta(hours=hours)

        if number_bans >= 3:
            await player.update(permaban=True).apply()

        await Ban.create(penguin_id=player.id, issued=date_issued, expires=date_expires,
                         moderator_id=p.id, reason=2, comment=comment, message=message)

        if penguin_id in p.server.penguins_by_id:
            if player.is_vanilla_client:
                await player.send_xt('ban', 612, 2, hours, comment)
                await player.close()
            else:
                await player.send_error_and_disconnect(610, comment)
