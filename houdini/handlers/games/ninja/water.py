import itertools
import math
import random
import asyncio
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Union
from houdini import IWaddle, handlers
from houdini.data.ninja import Card
from houdini.handlers import XTPacket
from houdini.penguin import Penguin

# made by diamondfern only desmondflame not anybody else... does not condone suicide. (you'll see)

@dataclass
class Played:
    id: int
    card: Card
    value: int
    element: str
    discard: bool

@dataclass
class Tile:
    id: int
    element: int # 0: fire 1: water 2: snow 3: none
    value: int
    seat: int

@dataclass
class Ninja:
    Sensei: bool
    penguin: Penguin
    deck: Dict[int, Played]
    chosen: Union[Played, None]
    synced: bool
    x: int
    y: int
    stonesCleared: int
    edgeCount: int
    tile: Union[Tile, None]

class CardJitsuWaterLogic(IWaddle):

    room_id = 995
    tile_iterator = card_iterator = 0
    tick = 60
    cardTimer = rowTimer = startTimer = None
    isReady = False
    RuleSet = {'f': 's', 'w': 'f', 's': 'w'}
    RuleSetValues = {'f': 0, 'w': 1, 's': 2, 'n': 3}
    RuleSetInvValues = {v: k for k, v in RuleSetValues.items()}

    RankSpeed = 1.0

    StampGroupId = 34

    def __init__(self, waddle):
        super().__init__(waddle)
        self.columns = 5 if len(waddle.penguins) <= 2 else 7
        x_vals = [1, 3, 5] if len(waddle.penguins) <= 3 else [1, 2, 4, 5]

        self.ninjas = {i: Ninja(
            penguin=waddle.penguins[i],
            Sensei=False,
            deck={},
            chosen=None,
            tile=None,
            synced=False,
            stonesCleared=0,
            edgeCount=0,
            x=x_vals[i],
            y=6
        ) for i in range(len(waddle.penguins))}

        self.board = []
        for i in range(self.columns):
            self.board.append([Tile(
                id=(_ + self.tile_iterator),
                element=random.randint((3 if _ < 2 else 0), (3 if _ < 2 else 2)),
                value=random.randint((0 if _ < 2 else 1), (0 if _ < 2 else 8)),
                seat=-1
            ) for _ in range(8)])
            self.tile_iterator += 8
        
        for player in self.ninjas.values():
            deck = Counter((card.card_id for card in player.penguin.cards.values() for _ in range(card.quantity + card.member_quantity)))
            deal = random.sample(list((deck)), 5)
            for card_id in deal:
                card = player.penguin.server.cards[card_id]
                player.deck[self.card_iterator] = Played(
                    id=self.card_iterator,
                    card=card,
                    value=card.value,
                    element=card.element,
                    discard=False)
                self.card_iterator += 1

        for seat, player in self.ninjas.items():
            self.board[player.x][1].seat = seat
            player.tile = self.board[player.x][1]

        self.startTimer = asyncio.create_task(self.tickCallback())

    async def handle_drown(self, winner_id):
        self.rowTimer.cancel()
        self.cardTimer.cancel()
        self.senseiontousTimer.cancel()
        await super().send_xt('zm', 'gw&' + str(winner_id) + '&0&00&false')
        rank = 2
        for row in self.board:
            for i in range(len(row)-1, -1, -1):
                curr_tile = row[i]
                if curr_tile.seat >= 0 and curr_tile.seat != winner_id:
                    await super().send_xt('zm', 'pd&' + str(curr_tile.seat) + '&' + str(rank) + '&00&false')
                    rank += 1
    
    async def remove_penguin(self, p, isQuit=True):
        if p.waddle is None or p.waddle.room_id != self.room_id:
            return
        seat_id = self.get_seat_id(p)
        player = self.ninjas[seat_id]     

        player.tile.seat = -1

        del self.ninjas[seat_id]
        await super().remove_penguin(p)

        if all([player.synced for player in self.ninjas.values()]):
            self.isReady = True
        if len(self.ninjas) < 1:
            if self.rowTimer is not None:
                self.rowTimer.cancel()
            if self.cardTimer is not None:
                self.cardTimer.cancel()

        await self.ninja_stamps_earned(p)
    
    async def tickCallback(self):
        try:
            while True:
                await asyncio.sleep(1)
                self.tick -= 1
                for player in self.ninjas.values():
                    await player.penguin.send_xt('zm', 'tt&' + str(self.tick))
                
                if self.isReady:
                    self.tick = 4
                    self.isReady = False
                            
                if self.tick < 0:
                    await super().send_xt('zm', 'pi&' + self.get_player_init_string())
                    self.startTimer = None
                    self.cardTimer = asyncio.create_task(self.cardCallback())
                    self.rowTimer = asyncio.create_task(self.rowCallback())
                    sensei = self.ninjas[1]
                    if sensei.Sensei:
                        self.senseiontousTimer = asyncio.create_task(self.find_sensei_path())
                    break
        except asyncio.CancelledError:
            pass

    async def cardCallback(self):
        try:
            self.tick = 0
            while True:
                await asyncio.sleep(2) 
                self.tick += 1
                for player in self.ninjas.values():
                    if self.tick >= 3:
                        player.deck.pop(min(player.deck.keys()), None)
                    deck = Counter((card.card_id for card in player.penguin.cards.values() for _ in range(card.quantity + card.member_quantity)))
                    dealt = Counter((played.card.id for played in player.deck.values() if played is not player.chosen))
                    difference = (list((deck - dealt).elements()))
                    random.shuffle(difference)
                    card_id = random.choice(difference)
                    card = player.penguin.server.cards[card_id]
                    player.deck[self.card_iterator] = Played(
                        id=self.card_iterator,
                        card=card,
                        value=card.value,
                        element=card.element,
                        discard=False)
                    await player.penguin.send_xt('zm', 'ca&' + str(card_id) + '-' + str(self.card_iterator))
                    self.card_iterator += 1
        except asyncio.CancelledError:
            pass
    
    async def rowCallback(self):
        try:
            while True:
                await asyncio.sleep(3)
                if len(self.board[0]) >= 10:
                    for i in range(self.columns):
                        tile = self.board[i][0]
                        if tile.seat != -1: # someones in it!
                            self.ninjas[tile.seat].edgeCount += 1
                
                await asyncio.sleep(2)

                board_row = ''
                for i in range(self.columns):
                    self.board[i].append(Tile(
                        id=self.tile_iterator,
                        element=random.randint(0, 2),
                        value=random.randint(1, 8),
                        seat=-1
                    ))
                    board_row += f'{self.board[i][-1].id}-{self.board[i][-1].element}-0{self.board[i][-1].value},'
                    self.tile_iterator += 1
                await super().send_xt('zm', 'br&' + board_row[:-1])

                if len(self.board[0]) >= 10:
                    for i in range(self.columns):
                        tile = self.board[i].pop(0)
                        if tile.seat != -1: # someones in it!
                            await self.ninjas[tile.seat].penguin.add_stamp(self.ninjas[tile.seat].penguin.server.stamps[274], notify=True)
                            await super().send_xt('zm', 'pk&' + str(tile.seat) + '&' + str(len(self.ninjas)) + '&00&false')
                            await self.remove_penguin(self.ninjas[tile.seat].penguin, False)
                            # ^ & dead place & amulet state , rank awarded & is sensei
        except asyncio.CancelledError:
            pass
    
    async def ninja_stamps_earned(self, p):
        game_stamps = [stamp for stamp in p.server.stamps.values() if stamp.group_id == p.room.stamp_group]
        collected_stamps = [stamp for stamp in game_stamps if stamp.id in p.stamps]
        total_collected_stamps = len(collected_stamps)
        total_game_stamps = len(game_stamps)
        collected_stamps_string = '|'.join(str(stamp.id) for stamp in collected_stamps)
        await p.send_xt('cjsi', collected_stamps_string, total_collected_stamps, total_game_stamps)
    
    def get_seat_id(self, p):
        for seat, player in self.ninjas.items():
            if player.penguin is p:
                return seat
        return -1
        
    def is_winning_row(self, tile_id):
        for i in range(self.columns):
            if self.board[i][-3].id == tile_id:
                return True
        return False
    
    def get_tile(self, tile_id, withCoordinates=False):
        for i in range(self.columns):
            for j in range(len(self.board[i])):
                if self.board[i][j].id == tile_id:
                    return (self.board[i][j], i, j) if withCoordinates else self.board[i][j]
        return None

    def find_neighbors(self, x, y):
        return [[self.board[i][j] if  i >= 0 and i < len(self.board) and j >= 0 and j < len(self.board[0]) else None
                for j in range(y-1-1, y+1)]
                    for i in range(x-1-1, x+1)]

    def get_player_init_string(self):
        sensei = self.ninjas[1]
        ninja = self.ninjas[0]
        if sensei.Sensei:
            return f'0|{ninja.penguin.safe_name}|{ninja.penguin.color}|{ninja.x},{ninja.y}&1|Sensei|14|{sensei.x},{sensei.y}'
        else:
            return '&'.join([f'{seat}|{player.penguin.safe_name}|{player.penguin.color}|{player.x},{player.y}' for seat, player in self.ninjas.items()])

    def fizzle_test(self, tile_element, card_element):
        #return True if tile_element in self.RuleSet and (self.RuleSet[tile_element] == card_element or tile_element != card_element) else False
        if tile_element in self.RuleSet:
            if self.RuleSet[tile_element] == card_element:
                return True
        return False

    def kills_element(self, tile_element, card_element):
        return True if tile_element in self.RuleSet and self.RuleSet[card_element] == tile_element else False

class WaterMatLogic(CardJitsuWaterLogic):
    RankSpeed = 0.0 # Practice

class WaterSenseiLogic(CardJitsuWaterLogic):
    RankSpeed = 0.0
    def __init__(self, waddle):
        super().__init__(waddle)

        self.ninjas[1] = Ninja(Sensei=True,penguin=waddle.penguins[0],deck={},chosen=None,tile=self.board[3][1],synced=True,stonesCleared=0,edgeCount=0,x=3,y=6)
        self.board[3][1].seat = 1

        self.isReady = True
        
    async def find_sensei_path(self):
        try:
            while True:
                ninja = self.ninjas[0]
                if ninja.penguin.water_ninja_rank >=4:
                    await asyncio.sleep(4)
                if ninja.penguin.water_ninja_rank <=3:
                    await asyncio.sleep(2)
                sensei = self.ninjas[1]
                board = self.board
                currentRow = sensei.x
                currentCell = sensei.y
                #print(board)
                tile = self.find_neighbors(currentRow,currentCell)[0][2]
                possibleOptions = 3 if currentCell != 6 else 2
                optionTried = 1
                SenseiLocation = f"{sensei.x},{sensei.y}" 
                elementIndex = 2
                newRow = currentRow + 1
                if sensei.stonesCleared == 0:
                    newRow = 2
                options={1:currentCell - 1 if currentCell != 0 else currentCell, 2:currentCell, 3:currentCell + 1}
                newCell = options.get(optionTried)
                if not newCell:
                    locationFound=True
                newcellrow = f"{newCell},{newRow}"
                if SenseiLocation != newcellrow:
                    newCellInfo = self.find_neighbors(newCell,newRow)[0][2]
                    if newCellInfo is None:
                        newCellInfo = self.find_neighbors(newCell,newRow)[0][2]
                    print(f"new retard: {newCellInfo}")
                    switcher={0:1, 1:2, 2:3}
                    elementIndex = switcher.get(int(newCellInfo.element),3)
                    tile.value = 0
                    tile.element = 3
                    if elementIndex != 3:
                        await self.send_xt('zm', 'pt&1&' + str(elementIndex) + '-' + str(newCellInfo.id) + '&' +
                                                     str(newCellInfo.id) + '-' + str(newCellInfo.element) + '-P0')
                    await self.send_xt('zm', 'pm&1-' + str(newCellInfo.id))
                    sensei.x = newCell
                    sensei.y = newRow
                    sensei.stonesCleared += 1
                    if self.is_winning_row(newCellInfo.id):
                        self.handle_drown(1)
                else:
                    print("Sensei tried to jump on the player, trying a different cell.")
                    optionTried += 1
        except asyncio.CancelledError:
            pass


### SENSEI SH#T ###

@handlers.handler(XTPacket('gz', ext='z'))
@handlers.waddle(WaterSenseiLogic)
async def handle_get_sensei_game(p):
    seat_id = p.waddle.get_seat_id(p)
    await p.send_xt('gz')
    await p.send_xt('jz')
    board_str = '|'.join(','.join([f'{p.waddle.board[col][row].id}-{p.waddle.board[col][row].element}-0{p.waddle.board[col][row].value}' for col in range(5)]) for row in range(8))
    await p.send_xt('zm', 'gi&250:bi&' + str(p.waddle.columns) + '&' + board_str + ':ci&' + '|'.join([f'{card.card.id}-{card.id}' for card in p.waddle.ninjas[seat_id].deck.values()]) + ':po&' + str(seat_id) + ':cv&64000.0&0.0:bv&7571.428571428572&3714.285714285714:tt&' + str(p.waddle.tick))

### REGULAR SH#T

@handlers.handler(XTPacket('zm', ext='z'), match=['110'])
@handlers.waddle(CardJitsuWaterLogic, WaterMatLogic)
async def handle_player_card_select(p, action: str, card_id: int):
    seat_id = p.waddle.get_seat_id(p)
    if card_id in p.waddle.ninjas[seat_id].deck:
        p.waddle.ninjas[seat_id].chosen = p.waddle.ninjas[seat_id].deck[card_id]

@handlers.handler(XTPacket('zm', ext='z'), match=['103'])
@handlers.waddle(CardJitsuWaterLogic, WaterMatLogic)
async def handle_game_start(p, action: str):
    seat_id = p.waddle.get_seat_id(p)
    p.waddle.ninjas[seat_id].synced = True
    if all([player.synced for player in p.waddle.ninjas.values()]):
        p.waddle.isReady = True

@handlers.handler(XTPacket('zm', ext='z'), match=['120'])
@handlers.waddle(CardJitsuWaterLogic, WaterMatLogic)
async def handle_player_move(p, action: str, tile_id: int):
    seat_id = p.waddle.get_seat_id(p)
    tile = p.waddle.get_tile(tile_id)
    if tile is not None and tile.value <= 0 and tile.seat == -1:
        ninja_obj = p.waddle.ninjas[seat_id]
        ninja_obj.tile.seat = -1
        tile.seat = seat_id
        ninja_obj.tile = tile
        await p.waddle.send_xt('zm', 'pm&' + str(seat_id) + '-' + str(tile.id))

        if p.waddle.is_winning_row(tile_id):
            await p.waddle.handle_drown(seat_id)
            await p.add_stamp(p.server.stamps[270], notify=True)
            if ninja_obj.stonesCleared >= 28:
                await p.add_stamp(p.server.stamps[288], notify=True)
            if ninja_obj.edgeCount >= 2:
                await p.add_stamp(p.server.stamps[286], notify=True)
            await p.update(water_matches_won=p.water_matches_won+1).apply()
            if p.water_matches_won == 100:
                await p.add_stamp(p.server.stamps[276], notify=True)

@handlers.handler(XTPacket('zm', ext='z'), match=['121'])
@handlers.waddle(CardJitsuWaterLogic, WaterMatLogic)
async def handle_player_throw(p, action: str, tile_id: int):
    seat_id = p.waddle.get_seat_id(p)
    tile, x, y = p.waddle.get_tile(tile_id, True)
    ninja_obj = p.waddle.ninjas[seat_id]
    if ninja_obj.chosen is not None and tile is not None:
        card = ninja_obj.chosen
        card_element = card.element
        if (p.waddle.fizzle_test(p.waddle.RuleSetInvValues[tile.element], card.element)):
            await p.send_xt('zm', 'pf&' + str(tile.element) + '-' + str(tile_id))
            return
        
        affected_tiles = [tile]
        if card.value >= 9: # power card
            surronding_tiles = p.waddle.find_neighbors(x, y)
            for cols in surronding_tiles:
                for curr_tile in cols:
                    if curr_tile is not None and (not p.waddle.fizzle_test(p.waddle.RuleSetInvValues[curr_tile.element], card.element)):
                        if (p.waddle.kills_element(p.waddle.RuleSetInvValues[curr_tile.element], card.element)):
                            curr_tile.value -= card.value // 3
                        elif curr_tile.element != 3:
                            curr_tile.value += card.value // 3
                        affected_tiles.append(curr_tile)

                        if curr_tile.value <= 0:
                            curr_tile.value = 0
                            curr_tile.element = 3
                            ninja_obj.stonesCleared += 1
        if (p.waddle.kills_element(p.waddle.RuleSetInvValues[tile.element], card.element)):
            tile.value -= card.value
            if card.value >= 9: # power card
                tile.value = 0 # need to clear surrondings as well
            #elif card.value >= 6:
            #    tile.value = 0 if tile.value <= 6 else (tile.value - random.randint(3,4))
            #else:
            #    tile.value = 0 if tile.value <= 3 else (tile.value - random.randint(3,4))
            
            # need more stuff
            if tile.value <= 0:
                tile.value = 0
                tile.element = 3
            ninja_obj.stonesCleared += 1
        elif tile.element != 3:
            tile.value += card.value

        ninja_obj.chosen = None
        await p.waddle.send_xt('zm', 'pt&' + str(seat_id) + '&' + str(p.waddle.RuleSetValues[card_element]) + '-' + str(tile_id) + '&' + '|'.join([f'{t.id}-{t.element}-{t.value}' for t in affected_tiles]))

@handlers.handler(XTPacket('gz', ext='z'))
@handlers.waddle(CardJitsuWaterLogic, WaterMatLogic)
async def handle_get_game(p):
    seat_id = p.waddle.get_seat_id(p)
    await p.send_xt('gz')
    await p.send_xt('jz')
    board_str = '|'.join(','.join([f'{p.waddle.board[col][row].id}-{p.waddle.board[col][row].element}-0{p.waddle.board[col][row].value}' for col in range(5)]) for row in range(8))
    await p.send_xt('zm', 'gi&250:bi&' + str(p.waddle.columns) + '&' + board_str + ':ci&' + '|'.join([f'{card.card.id}-{card.id}' for card in p.waddle.ninjas[seat_id].deck.values()]) + ':po&' + str(seat_id) + ':cv&64000.0&0.0:bv&7571.428571428572&3714.285714285714:tt&' + str(p.waddle.tick))
    # gi&250:bi
    # will have to edit cols ^ its 5 bi&
