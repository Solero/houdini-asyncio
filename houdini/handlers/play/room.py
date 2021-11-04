import random

from houdini import handlers
from houdini.data.penguin import Penguin
from houdini.handlers import XTPacket


@handlers.handler(XTPacket('r', 'cdu'))
@handlers.cooldown(1)
async def handle_get_coin_reward(p):
    if random.random() < 0.3:
        coins = random.choice([1, 2, 5, 10, 20, 50, 100])
        await p.update(coins=Penguin.coins + coins).apply()
        await p.send_xt('cdu', coins, p.coins)
		
@handlers.handler(XTPacket('r', 'gtc'))
@handlers.cooldown(1)
async def handle_get_coins(p):
    # Fetch coins from the database
    p.coins, = await Penguin.select('coins').where(Penguin.id == p.id).gino.first()
    await p.send_xt("gtc", p.coins)

