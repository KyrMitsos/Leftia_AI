from decimal import Decimal
import statistics

BOOK_MIN = 0.80
BOOK_MAX = 1.50
BOOK_TARGET = 1.025
HISTORY_LIMIT = 8
MIN_SPREAD_SAMPLES = 3


def normalise_id(value):
    try:
        return str(int(str(value).strip()))
    except Exception:
        return str(value).strip()


def same_id(a, b):
    return normalise_id(a) == normalise_id(b)


def book_sum(prices):
    if len(prices) != 3 or any(price is None or price <= 1.0 for price in prices):
        return None
    return sum(1.0 / price for price in prices)


def book_is_plausible(prices, low=BOOK_MIN, high=BOOK_MAX):
    value = book_sum(prices)
    return value is not None and low <= value <= high


def _classic_ladder():
    bands = [
        (Decimal('1.01'), Decimal('2.00'), Decimal('0.01')),
        (Decimal('2.00'), Decimal('3.00'), Decimal('0.02')),
        (Decimal('3.00'), Decimal('4.00'), Decimal('0.05')),
        (Decimal('4.00'), Decimal('6.00'), Decimal('0.10')),
        (Decimal('6.00'), Decimal('10.00'), Decimal('0.20')),
        (Decimal('10.00'), Decimal('20.00'), Decimal('0.50')),
        (Decimal('20.00'), Decimal('30.00'), Decimal('1.00')),
        (Decimal('30.00'), Decimal('50.00'), Decimal('2.00')),
        (Decimal('50.00'), Decimal('100.00'), Decimal('5.00')),
        (Decimal('100.00'), Decimal('1000.00'), Decimal('10.00')),
    ]
    values = []
    for start, end, step in bands:
        value = start
        while value < end:
            values.append(float(value))
            value += step
    values.append(1000.0)
    return values


CLASSIC_LADDER = _classic_ladder()
LADDER_INDEX = {round(value, 2): index for index, value in enumerate(CLASSIC_LADDER)}


def _ladder_index(price):
    if price is None:
        return None
    return LADDER_INDEX.get(round(float(price), 2))


def move_ticks(price, ticks):
    index = _ladder_index(price)
    if index is None:
        return None
    target = min(max(index + int(ticks), 0), len(CLASSIC_LADDER) - 1)
    return CLASSIC_LADDER[target]


def spread_ticks(back, lay):
    back_index = _ladder_index(back)
    lay_index = _ladder_index(lay)
    if back_index is None or lay_index is None or lay_index < back_index:
        return None
    return lay_index - back_index


def best_price(exchange, side):
    offers = exchange.get(side, []) if isinstance(exchange, dict) else []
    if not offers:
        return None
    price = offers[0].get('price')
    try:
        return float(price)
    except Exception:
        return None


def market_snapshot(event_node, market_id, selection_ids):
    markets = event_node.get('marketNodes', []) if isinstance(event_node, dict) else []
    market = next((item for item in markets if same_id(item.get('marketId'), market_id)), None)
    if market is None:
        return None

    runners = {normalise_id(item.get('selectionId')): item for item in market.get('runners', [])}
    back = []
    lay = []
    exchanges = []
    for selection_id in selection_ids:
        runner = runners.get(normalise_id(selection_id), {})
        exchange = runner.get('exchange', {})
        exchanges.append(exchange)
        back.append(best_price(exchange, 'availableToBack'))
        lay.append(best_price(exchange, 'availableToLay'))

    state = market.get('state', {}) if isinstance(market, dict) else {}
    inplay = state.get('inplay')
    if inplay is None:
        inplay = state.get('inPlay')

    return {
        'event_id': normalise_id(event_node.get('eventId')),
        'market_id': normalise_id(market_id),
        'back': back,
        'lay': lay,
        'exchanges': exchanges,
        'book': book_sum(back),
        'inplay': inplay,
        'status': state.get('status'),
    }


def expected_book(history):
    books = [entry.get('book') for entry in history if entry.get('book') is not None and BOOK_MIN <= entry.get('book') <= BOOK_MAX]
    if not books:
        return BOOK_TARGET
    return statistics.median(books[-HISTORY_LIMIT:])


def recent_clean(history):
    return [entry for entry in history if book_is_plausible(entry.get('back', []))][-HISTORY_LIMIT:]


def snapshot_is_strong(snapshot, history):
    if snapshot is None or not book_is_plausible(snapshot.get('back', [])):
        return False
    target = expected_book(history)
    return abs(snapshot['book'] - target) <= 0.12


def choose_complete_snapshot(candidates, history):
    target = expected_book(history)
    valid = [entry for entry in candidates if book_is_plausible(entry.get('back', []))]
    if not valid:
        return None
    return min(valid, key=lambda entry: abs(entry['book'] - target))


def _runner_anchor(history, runner_index):
    values = [entry['back'][runner_index] for entry in recent_clean(history) if entry['back'][runner_index] is not None]
    return statistics.median(values) if values else None


def _tick_distance(a, b):
    ai = _ladder_index(a)
    bi = _ladder_index(b)
    if ai is None or bi is None:
        return 9999
    return abs(ai - bi)



def boundary_snapshots_close(first, second, max_runner_ticks=2, max_total_ticks=4, max_book_delta=0.03):
    if first is None or second is None:
        return False
    first_back = first.get('back', [])
    second_back = second.get('back', [])
    if len(first_back) != 3 or len(second_back) != 3:
        return False
    if any(value is None or value <= 1.0 for value in first_back + second_back):
        return False
    distances = [_tick_distance(a, b) for a, b in zip(first_back, second_back)]
    if any(distance > max_runner_ticks for distance in distances):
        return False
    if sum(distances) > max_total_ticks:
        return False
    first_book = book_sum(first_back)
    second_book = book_sum(second_back)
    if first_book is None or second_book is None:
        return False
    return abs(first_book - second_book) <= max_book_delta

def mix_candidates(candidates, history):
    target = expected_book(history)
    pools = []
    for runner_index in range(3):
        values = []
        for entry in candidates:
            price = entry.get('back', [None, None, None])[runner_index]
            if price is not None and price > 1.0 and price not in values:
                values.append(price)
        anchor = _runner_anchor(history, runner_index)
        if anchor is not None:
            values.sort(key=lambda value: _tick_distance(value, anchor))
        pools.append(values[:5])

    if any(not pool for pool in pools):
        return None

    anchors = [_runner_anchor(history, index) for index in range(3)]
    best = None
    for home in pools[0]:
        for away in pools[1]:
            for draw in pools[2]:
                prices = [home, away, draw]
                book = book_sum(prices)
                if book is None or not BOOK_MIN <= book <= BOOK_MAX:
                    continue
                anchor_penalty = 0
                for index, price in enumerate(prices):
                    if anchors[index] is not None:
                        anchor_penalty += min(_tick_distance(price, anchors[index]), 50) / 50.0
                score = abs(book - target) + (0.10 * anchor_penalty)
                if best is None or score < best['score']:
                    best = {'back': prices, 'book': book, 'score': score}
    return best


def stable_spread(history, runner_index):
    spreads = []
    for entry in recent_clean(history):
        back = entry.get('back', [None, None, None])[runner_index]
        lay = entry.get('lay', [None, None, None])[runner_index]
        spread = spread_ticks(back, lay)
        if spread is not None:
            spreads.append(spread)
    if len(spreads) < MIN_SPREAD_SAMPLES:
        return None
    recent = spreads[-HISTORY_LIMIT:]
    median = int(round(statistics.median(recent)))
    if max(recent) - min(recent) > max(3, median):
        return None
    return median


def infer_back_from_lay(lay, history, runner_index):
    spread = stable_spread(history, runner_index)
    if lay is None or spread is None:
        return None
    return move_ticks(lay, -spread)


def infer_back_from_partial_book(snapshot, history, runner_index, max_ticks=12):
    """Infer one missing BACK from its LAY and the other two BACK prices.

    This is deliberately conservative. It is mainly for boundary books such as
    LAY 1.01 with no BACK while the other two runners are very large.
    """
    if snapshot is None:
        return None
    backs = list(snapshot.get('back', []))
    lays = list(snapshot.get('lay', []))
    if len(backs) != 3 or len(lays) != 3:
        return None
    if sum(value is None for value in backs) != 1 or backs[runner_index] is not None:
        return None

    lay = lays[runner_index]
    lay_index = _ladder_index(lay)
    if lay_index is None:
        return None
    if any(backs[index] is None or backs[index] <= 1.0 for index in range(3) if index != runner_index):
        return None

    target = expected_book(history)
    anchor = _runner_anchor(history, runner_index)
    best = None
    for ticks in range(0, min(max_ticks, lay_index) + 1):
        candidate = move_ticks(lay, -ticks)
        if candidate is None or candidate <= 1.0 or candidate > lay:
            continue
        prices = list(backs)
        prices[runner_index] = candidate
        book = book_sum(prices)
        if book is None or not BOOK_MIN <= book <= BOOK_MAX:
            continue

        # Prefer a coherent whole book, then a price close to the available LAY.
        # If a recent clean runner anchor exists, use it as additional evidence.
        score = abs(book - target) + (0.002 * ticks)
        if anchor is not None:
            score += 0.02 * min(_tick_distance(candidate, anchor), 25) / 25.0
        if best is None or score < best['score']:
            best = {'price': candidate, 'book': book, 'score': score}

    return best


def repair_missing_back(snapshot, history):
    if snapshot is None:
        return None
    prices = list(snapshot.get('back', []))
    if len(prices) != 3:
        return None
    changed = []
    for runner_index in range(3):
        if prices[runner_index] is None:
            inferred = infer_back_from_lay(snapshot.get('lay', [None, None, None])[runner_index], history, runner_index)
            if inferred is None:
                partial = infer_back_from_partial_book(snapshot, history, runner_index)
                inferred = partial['price'] if partial is not None else None
            if inferred is not None:
                prices[runner_index] = inferred
                changed.append((runner_index, inferred))
    book = book_sum(prices)
    if book is None or not BOOK_MIN <= book <= BOOK_MAX:
        return None
    return {'back': prices, 'book': book, 'inferred': changed}



def repair_match_odds_boundary(snapshot, history, longshot_floor=100.0):
    """Complete genuine Match Odds boundary books without inventing mid-range prices.

    Betfair can leave one side empty when an outcome is effectively at an
    exchange limit.  For an otherwise coherent open market we represent that
    missing liquidity at 1.01 or 1000.0.  This helper is for MATCH_ODDS only;
    it must not be used to manufacture prices for settled/impossible OU lines.
    """
    if snapshot is None:
        return None

    status = str(snapshot.get('status') or '').upper()
    if status in {'SUSPENDED', 'CLOSED'}:
        return None

    backs = list(snapshot.get('back', []))
    lays = list(snapshot.get('lay', []))
    if len(backs) != 3 or len(lays) != 3:
        return None

    inferred = []

    repaired = repair_missing_back(snapshot, history)
    if repaired is not None:
        backs = list(repaired['back'])
        inferred.extend(('back', index, value) for index, value in repaired.get('inferred', []))
    elif any(value is None for value in backs):
        # Exact exchange-limit quotes on the opposite side are strong evidence
        # for the same boundary price when that completes a coherent book.
        trial = list(backs)
        trial_inferred = []
        for index, value in enumerate(trial):
            if value is not None:
                continue
            lay = lays[index]
            if lay == 1.01:
                trial[index] = 1.01
                trial_inferred.append(('back', index, 1.01))
            elif lay == 1000.0:
                trial[index] = 1000.0
                trial_inferred.append(('back', index, 1000.0))
        if book_is_plausible(trial):
            backs = trial
            inferred.extend(trial_inferred)

    if not book_is_plausible(backs):
        return None

    # Missing LAY liquidity at the hard limits is represented by the hard
    # limit itself.  Mid-range missing lays remain missing; we do not invent
    # an ordinary spread just to make the row complete.
    for index, lay in enumerate(lays):
        if lay is not None:
            continue
        back = backs[index]
        if back == 1.01:
            lays[index] = 1.01
            inferred.append(('lay', index, 1.01))
        elif back is not None and back >= longshot_floor:
            lays[index] = 1000.0
            inferred.append(('lay', index, 1000.0))

    return {
        'back': backs,
        'lay': lays,
        'book': book_sum(backs),
        'inferred': inferred,
    }

def repair_suspect_back(prices, candidates, history):
    clean = recent_clean(history)
    if not clean or len(prices) != 3:
        return None

    anchors = [_runner_anchor(history, index) for index in range(3)]
    if any(anchor is None for anchor in anchors):
        return None

    suspect = max(range(3), key=lambda index: _tick_distance(prices[index], anchors[index]))
    lay = None
    for snapshot in reversed(candidates):
        value = snapshot.get('lay', [None, None, None])[suspect]
        if value is not None:
            lay = value
            break

    inferred = infer_back_from_lay(lay, history, suspect)
    if inferred is None:
        return None

    repaired = list(prices)
    repaired[suspect] = inferred
    book = book_sum(repaired)
    if book is None or not BOOK_MIN <= book <= BOOK_MAX:
        return None

    target = expected_book(history)
    old_book = book_sum(prices)
    if old_book is not None and abs(book - target) >= abs(old_book - target):
        return None
    return {'back': repaired, 'book': book, 'inferred': [(suspect, inferred)]}


def latest_consistent(history):
    clean = recent_clean(history)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[-1]

    target = expected_book(clean)
    for entry in reversed(clean):
        if abs(entry['book'] - target) <= 0.12:
            return entry
    return min(clean, key=lambda entry: abs(entry['book'] - target))
