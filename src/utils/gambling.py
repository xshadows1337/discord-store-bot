"""
AbyssHub Gambling System
Coin-based economy: deposit real money → coins → gamble → spend coins on products.

Coin rate: $1 = 10 coins  (1 coin = $0.10)

Games:
  - Coin Flip: 2× or 0×  (48% win)
  - Dice Roll: bet over/under a number (variable payout)
  - Mines: Minesweeper-style, cash out anytime (escalating multiplier)
"""

import json
import os
import random
import secrets
import sqlite3
import time
from pathlib import Path

from loguru import logger

_DB_PATH = Path(__file__).parent.parent / 'users.db'

COIN_RATE = 10  # coins per $1 USD  (1 coin = $0.10)

# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    # Ensure coins column exists
    try:
        conn.execute('SELECT coins FROM users LIMIT 1')
    except sqlite3.OperationalError:
        conn.execute('ALTER TABLE users ADD COLUMN coins INTEGER NOT NULL DEFAULT 0')
        conn.commit()
    # Gambling history table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gambling_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            game        TEXT    NOT NULL,
            bet         INTEGER NOT NULL,
            multiplier  REAL    NOT NULL,
            payout      INTEGER NOT NULL,
            result      TEXT,
            created_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
        )
    ''')
    # Coin transactions table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS coin_transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            type        TEXT    NOT NULL,
            amount      INTEGER NOT NULL,
            balance     INTEGER NOT NULL,
            note        TEXT,
            created_at  REAL    NOT NULL DEFAULT (strftime('%s','now'))
        )
    ''')
    conn.commit()
    return conn


# ── Balance ───────────────────────────────────────────────────────────────────

def get_balance(user_id: int) -> int:
    db = _get_db()
    row = db.execute('SELECT coins FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()
    return row['coins'] if row else 0


def add_coins(user_id: int, amount: int, note: str = '') -> int:
    """Add coins to user balance. Returns new balance."""
    db = _get_db()
    db.execute('UPDATE users SET coins = coins + ? WHERE id = ?', (amount, user_id))
    row = db.execute('SELECT coins FROM users WHERE id = ?', (user_id,)).fetchone()
    new_bal = row['coins']
    db.execute(
        'INSERT INTO coin_transactions (user_id, type, amount, balance, note) VALUES (?,?,?,?,?)',
        (user_id, 'credit', amount, new_bal, note)
    )
    db.commit()
    db.close()
    return new_bal


def deduct_coins(user_id: int, amount: int, note: str = '') -> tuple[bool, int]:
    """Deduct coins. Returns (success, new_balance)."""
    db = _get_db()
    row = db.execute('SELECT coins FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row or row['coins'] < amount:
        db.close()
        return False, row['coins'] if row else 0
    db.execute('UPDATE users SET coins = coins - ? WHERE id = ?', (amount, user_id))
    row2 = db.execute('SELECT coins FROM users WHERE id = ?', (user_id,)).fetchone()
    new_bal = row2['coins']
    db.execute(
        'INSERT INTO coin_transactions (user_id, type, amount, balance, note) VALUES (?,?,?,?,?)',
        (user_id, 'debit', amount, new_bal, note)
    )
    db.commit()
    db.close()
    return True, new_bal


def _record_game(user_id: int, game: str, bet: int, multiplier: float, payout: int, result: str):
    db = _get_db()
    db.execute(
        'INSERT INTO gambling_history (user_id, game, bet, multiplier, payout, result) VALUES (?,?,?,?,?,?)',
        (user_id, game, bet, multiplier, payout, result)
    )
    db.commit()
    db.close()


# ── Coin Flip (48% win → 2× payout) ─────────────────────────────────────────

def coinflip(user_id: int, bet: int, choice: str) -> dict:
    """
    choice: 'heads' or 'tails'
    House edge ~4%: win probability = 48%
    """
    if bet < 2:
        return {'ok': False, 'msg': 'Minimum bet is 2 coins ($0.20).'}
    if choice not in ('heads', 'tails'):
        return {'ok': False, 'msg': 'Choose heads or tails.'}

    ok, bal = deduct_coins(user_id, bet, f'Coinflip bet ({choice})')
    if not ok:
        return {'ok': False, 'msg': 'Insufficient coins.', 'balance': bal}

    # 48% win chance (house edge)
    roll = random.random()
    outcome = 'heads' if roll < 0.50 else 'tails'
    won = outcome == choice

    if won:
        payout = bet * 2
        new_bal = add_coins(user_id, payout, 'Coinflip win')
        _record_game(user_id, 'coinflip', bet, 2.0, payout, f'{outcome} — WIN')
        return {'ok': True, 'won': True, 'outcome': outcome, 'payout': payout, 'balance': new_bal}
    else:
        _record_game(user_id, 'coinflip', bet, 0.0, 0, f'{outcome} — LOSS')
        return {'ok': True, 'won': False, 'outcome': outcome, 'payout': 0, 'balance': bal}


# ── Dice Roll (over/under) ───────────────────────────────────────────────────

def dice_roll(user_id: int, bet: int, target: int, direction: str) -> dict:
    """
    Roll 1-100. Bet over or under a target.
    Payout = 98 / win_probability  (2% house edge)
    """
    if bet < 2:
        return {'ok': False, 'msg': 'Minimum bet is 2 coins ($0.20).'}
    if target < 5 or target > 95:
        return {'ok': False, 'msg': 'Target must be between 5 and 95.'}
    if direction not in ('over', 'under'):
        return {'ok': False, 'msg': 'Choose over or under.'}

    if direction == 'over':
        win_prob = (100 - target) / 100
    else:
        win_prob = (target - 1) / 100

    if win_prob <= 0:
        return {'ok': False, 'msg': 'Invalid target.'}

    multiplier = round(0.98 / win_prob, 2)  # 2% house edge
    multiplier = min(multiplier, 50.0)

    ok, bal = deduct_coins(user_id, bet, f'Dice bet ({direction} {target})')
    if not ok:
        return {'ok': False, 'msg': 'Insufficient coins.', 'balance': bal}

    roll = random.randint(1, 100)
    won = (direction == 'over' and roll > target) or (direction == 'under' and roll < target)

    if won:
        payout = int(bet * multiplier)
        new_bal = add_coins(user_id, payout, f'Dice win (rolled {roll})')
        _record_game(user_id, 'dice', bet, multiplier, payout, f'Rolled {roll} — {direction} {target} — WIN')
        return {'ok': True, 'won': True, 'roll': roll, 'multiplier': multiplier, 'payout': payout, 'balance': new_bal}
    else:
        _record_game(user_id, 'dice', bet, 0.0, 0, f'Rolled {roll} — {direction} {target} — LOSS')
        return {'ok': True, 'won': False, 'roll': roll, 'multiplier': multiplier, 'payout': 0, 'balance': bal}


# ── Mines ─────────────────────────────────────────────────────────────────────
# 5×5 grid, X mines hidden. Click safe tiles for escalating multiplier. Cash out anytime.

_active_mines: dict[int, dict] = {}  # user_id → game state

def mines_start(user_id: int, bet: int, mine_count: int = 5) -> dict:
    if bet < 2:
        return {'ok': False, 'msg': 'Minimum bet is 2 coins ($0.20).'}
    if mine_count < 1 or mine_count > 24:
        return {'ok': False, 'msg': 'Mine count must be 1-24.'}
    if user_id in _active_mines:
        return {'ok': False, 'msg': 'You already have an active Mines game. Cash out or finish it first.'}

    ok, bal = deduct_coins(user_id, bet, f'Mines bet ({mine_count} mines)')
    if not ok:
        return {'ok': False, 'msg': 'Insufficient coins.', 'balance': bal}

    # Place mines randomly on 5×5 grid (0-24)
    mines = set(random.sample(range(25), mine_count))
    _active_mines[user_id] = {
        'bet': bet,
        'mines': mines,
        'mine_count': mine_count,
        'revealed': set(),
        'started_at': time.time(),
    }
    return {'ok': True, 'balance': bal, 'mine_count': mine_count, 'grid_size': 25}


def _mines_multiplier(revealed: int, mine_count: int) -> float:
    """Calculate multiplier for mines based on revealed safe tiles."""
    safe_total = 25 - mine_count
    if revealed == 0:
        return 1.0
    # Each reveal: mult *= safe_remaining / tiles_remaining (with 2% edge)
    mult = 0.98
    for i in range(revealed):
        remaining_safe = safe_total - i
        remaining_total = 25 - i
        mult *= remaining_total / remaining_safe
    return round(mult, 2)


def mines_reveal(user_id: int, tile: int) -> dict:
    game = _active_mines.get(user_id)
    if not game:
        return {'ok': False, 'msg': 'No active game.'}
    if tile < 0 or tile > 24:
        return {'ok': False, 'msg': 'Invalid tile (0-24).'}
    if tile in game['revealed']:
        return {'ok': False, 'msg': 'Tile already revealed.'}

    if tile in game['mines']:
        # Hit a mine — game over
        bet = game['bet']
        del _active_mines[user_id]
        bal = get_balance(user_id)
        _record_game(user_id, 'mines', bet, 0.0, 0, f'Hit mine at tile {tile} — LOSS')
        return {'ok': True, 'mine': True, 'payout': 0, 'balance': bal, 'mines': list(game['mines'])}

    game['revealed'].add(tile)
    mult = _mines_multiplier(len(game['revealed']), game['mine_count'])
    potential = int(game['bet'] * mult)
    safe_left = (25 - game['mine_count']) - len(game['revealed'])

    return {
        'ok': True, 'mine': False, 'tile': tile,
        'revealed_count': len(game['revealed']),
        'multiplier': mult, 'potential_payout': potential,
        'safe_remaining': safe_left,
    }


def mines_cashout(user_id: int) -> dict:
    game = _active_mines.get(user_id)
    if not game:
        return {'ok': False, 'msg': 'No active game.'}
    if not game['revealed']:
        # Can't cash out with 0 reveals — just return bet
        del _active_mines[user_id]
        new_bal = add_coins(user_id, game['bet'], 'Mines — cancelled (0 reveals)')
        return {'ok': True, 'payout': game['bet'], 'multiplier': 1.0, 'balance': new_bal, 'mines': list(game['mines'])}

    mult = _mines_multiplier(len(game['revealed']), game['mine_count'])
    payout = int(game['bet'] * mult)
    del _active_mines[user_id]
    new_bal = add_coins(user_id, payout, f'Mines cashout ({len(game["revealed"])} reveals, {mult}x)')
    _record_game(user_id, 'mines', game['bet'], mult, payout, f'Cashout at {len(game["revealed"])} reveals — WIN')
    return {'ok': True, 'payout': payout, 'multiplier': mult, 'balance': new_bal, 'mines': list(game['mines'])}


# ── History ───────────────────────────────────────────────────────────────────

def get_history(user_id: int, limit: int = 20) -> list[dict]:
    db = _get_db()
    rows = db.execute(
        'SELECT game, bet, multiplier, payout, result, created_at FROM gambling_history WHERE user_id = ? ORDER BY id DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_transactions(user_id: int, limit: int = 20) -> list[dict]:
    db = _get_db()
    rows = db.execute(
        'SELECT type, amount, balance, note, created_at FROM coin_transactions WHERE user_id = ? ORDER BY id DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]
