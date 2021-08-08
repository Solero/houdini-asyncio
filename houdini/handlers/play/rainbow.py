import time
from datetime import datetime, timedelta

import ujson

from houdini import handlers
from houdini.constants import ClientType
from houdini.handlers import XTPacket

RainbowQuestRewards = [6158, 4809, 1560, 3159]
RainbowBonusReward = 5220
RainbowQuestWait = timedelta(minutes=60)
RainbowQuestWaitMember = timedelta(minutes=20)


@handlers.handler(XTPacket('rpq', 'rpqtc'), client=ClientType.Vanilla)
async def handle_rainbow_puffle_task_complete(p, task_id: int):
    current_datetime = datetime.now()
    current_task = await p.server.redis.get(f'houdini.rainbow_task.{p.id}') or 0

    if int(current_task) < len(RainbowQuestRewards) and int(current_task) == task_id:
        task_completion = await p.server.redis.get(f'houdini.rainbow_completion.{p.id}') or time.time()

        quest_wait = RainbowQuestWaitMember if p.is_member else RainbowQuestWait

        if int(current_task) == 0 or current_datetime - datetime.fromtimestamp(int(task_completion)) > quest_wait:
            if int(task_id) == len(RainbowQuestRewards) - 1:
                await p.update(rainbow_adoptability=True).apply()

            progression_expiry = (current_datetime + timedelta(days=30))
            await p.server.redis.incr(f'houdini.rainbow_task.{p.id}')
            await p.server.redis.set(f'houdini.rainbow_completion.{p.id}', int(time.time()))
            await p.server.redis.expireat(f'houdini.rainbow_task.{p.id}', progression_expiry)
            await p.server.redis.expireat(f'houdini.rainbow_completion.{p.id}', progression_expiry)


@handlers.handler(XTPacket('rpq', 'rpqd'), client=ClientType.Vanilla)
async def handle_rainbow_quest_cookie(p):
    current_task = await p.server.redis.get(f'houdini.rainbow_task.{p.id}') or 0
    current_task = int(current_task)

    if current_task == len(RainbowQuestRewards) and not p.rainbow_adoptability:
        await p.server.redis.delete(f'houdini.rainbow_task.{p.id}',
                                    f'houdini.rainbow_completion.{p.id}',
                                    f'houdini.rainbow_coins.{p.id}')
        current_task = 0

    current_datetime = datetime.now()
    task_completion = await p.server.redis.get(f'houdini.rainbow_completion.{p.id}')
    coins_collected = await p.server.redis.smembers(f'houdini.rainbow_coins.{p.id}')

    if task_completion:
        quest_wait = RainbowQuestWaitMember if p.is_member else RainbowQuestWait
        task_availability = datetime.fromtimestamp(int(task_completion)) + quest_wait

        minutes_remaining = int((task_availability - current_datetime).total_seconds() // 60)
        task_availability_unix = task_availability.timestamp()
    else:
        minutes_remaining = 0
        task_availability_unix = 0

    has_bonus = int(current_task == len(RainbowQuestRewards) and 'bonus' not in coins_collected)

    tasks = {
        'currTask': min(current_task, len(RainbowQuestRewards) - 1),
        'taskAvail': int(task_availability_unix),
        'bonus': has_bonus,
        'cannon': p.rainbow_adoptability,
        'questsDone': current_task,
        'hoursRemaining': '0',
        'minutesRemaining': str(max(0, minutes_remaining + 1)),
        'tasks': {
            task_id: {
                'item': 2 if RainbowQuestRewards[task_id] in p.inventory else 1 if p.is_member else 0,
                'coin': 2 if str(task_id) in coins_collected else 1 if task_id < current_task else 0,
                'completed': bool(task_id < current_task)
            } for task_id in range(len(RainbowQuestRewards))
        }
    }

    return await p.send_xt('rpqd', ujson.dumps(tasks))


@handlers.handler(XTPacket('rpq', 'rpqcc'), client=ClientType.Vanilla)
async def handle_rainbow_puffle_task_coin_collected(p, task_id: int):
    current_task = await p.server.redis.get(f'houdini.rainbow_task.{p.id}')
    coins_collected = await p.server.redis.sismember(f'houdini.rainbow_coins.{p.id}', task_id)
    if task_id <= int(current_task) and not coins_collected:
        await p.server.redis.sadd(f'houdini.rainbow_coins.{p.id}', task_id)
        await p.server.redis.expireat(f'houdini.rainbow_coins.{p.id}',
                                      (datetime.now() + timedelta(days=30)))
        await p.update(coins=p.coins + 150).apply()
        await p.send_xt('rpqcc', task_id, 2, p.coins)


@handlers.handler(XTPacket('rpq', 'rpqic'), client=ClientType.Vanilla)
async def handle_rainbow_puffle_task_item_collected(p, task_id: int):
    current_task = await p.server.redis.get(f'houdini.rainbow_task.{p.id}')
    if task_id <= int(current_task):
        item_id = RainbowQuestRewards[task_id]
        await p.add_inventory(p.server.items[item_id], notify=False)
        await p.send_xt('rpqic', task_id, 2)


@handlers.handler(XTPacket('rpq', 'rpqbc'), client=ClientType.Vanilla)
async def handle_rainbow_puffle_task_bonus_collected(p):
    if p.rainbow_adoptability:
        if RainbowBonusReward not in p.inventory:
            await p.add_inventory(p.server.items[RainbowBonusReward])
            await p.server.redis.sadd(f'houdini.rainbow_coins.{p.id}', 'bonus')
        else:
            coins_collected = await p.server.redis.sismember(f'houdini.rainbow_coins.{p.id}', 'bonus')
            if not coins_collected:
                await p.server.redis.sadd(f'houdini.rainbow_coins.{p.id}', 'bonus')
                await p.update(coins=p.coins + 500).apply()
                await p.send_xt('rpqbc', 0, 0, p.coins)
