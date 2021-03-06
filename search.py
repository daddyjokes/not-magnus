"""
Not Magnus
Learner classical chess engine by Devin Zhang

Search functions which navigate the game tree
"""
from sys import stdout
from evaluate import *


def qsearch(board, alpha, beta, movetime = INF, stop = lambda: False):
    """
    Quiescence search to extend search depth until
    there are no more captures or checks
    """
    global nodes
    
    if can_exit_search(movetime, stop, start_time):
        return 0

    stand_pat = evaluate(board)
    nodes += 1
    
    if stand_pat >= beta:
        return beta
    if not board.is_check():
        alpha = max(alpha, stand_pat)

    moves = list(board.generate_legal_moves())
    moves.sort(key = lambda move : rate(board, move, None), reverse = True) # Significant improvements if sorted
    for move in moves:
        if board.is_capture(move) or board.gives_check(move):
            board.push(move)
            score = -qsearch(board, -beta, -alpha, movetime, stop)
            board.pop()

            if score >= beta:
                return beta
            alpha = max(alpha, score)

    return alpha


def negamax(board, depth, alpha, beta, movetime = INF, stop = lambda: False):
    """
    Searches the possible moves using negamax, alpha-beta pruning, transposition table,
    quiescence search, null move pruning, and late move reduction
    Initial psuedocode adapated from Jeroen W.T. Carolus
    """
    global nodes
    
    if can_exit_search(movetime, stop, start_time):
        return (None, 0)

    key = board._transposition_key()
    tt_move = None

    # Search for position in the transposition table
    if key in ttable:
        tt_depth, tt_move, tt_score, flag = ttable[key]
        if tt_depth >= depth:
            if tt_score != 0: # Prevent mistakingly detecting this position as draw by repetition due to transposition in another branch
                nodes += 1
                if flag == "EXACT":
                    return (tt_move, tt_score)
                elif flag == "LOWERBOUND":
                    alpha = max(alpha, tt_score)
                elif flag == "UPPERBOUND":
                    beta = min(beta, tt_score)
                if alpha >= beta:
                    return (tt_move, tt_score)

    old_alpha = alpha
    if depth <= 0 or is_game_over(board):
        score = qsearch(board, alpha, beta, movetime, stop)
        return (None, score)
    else:
        # Null move pruning
        if null_move_ok(board):
            null_move_depth_reduction = 2
            board.push(chess.Move.null())
            score = -negamax(board, depth - 1 - null_move_depth_reduction, -beta, -beta + 1, movetime, stop)[1]
            board.pop()
            nodes -= 1
            if score >= beta:
                return (None, score)

        # Alpha-beta negamax
        score = -INF
        best_move = None
        best_score = -INF
        moves = board.generate_legal_moves()
        moves = sorted(moves, key = lambda move : rate(board, move, tt_move), reverse = True)

        moves_searched = 0
        has_failed_high = False

        for move in moves:
            board.push(move)

            # Append to threefold repetition table
            if key in rtable:
                rtable[key] += 1
            else:
                rtable[key] = 1
            
            # Late move reduction
            late_move_depth_reduction = 0
            if reduction_ok(board, depth, move, moves_searched, has_failed_high):
                late_move_depth_reduction = 1

            score = -negamax(board, depth - 1 - late_move_depth_reduction, -beta, -alpha, movetime, stop)[1]
            moves_searched += 1

            board.pop()

            # Remove from threefold repetition table
            rtable[key] -= 1

            if score > best_score:
                best_move = move
                best_score = score

            alpha = max(alpha, best_score)

            if alpha >= beta: # Beta cut-off (fails high)
                has_failed_high = True
                if not board.is_capture(move):
                    htable[board.piece_at(move.from_square).color][move.from_square][move.to_square] += depth**2 # Update history heuristic table
                break
        
        # Add position to the transposition tables
        if best_score <= old_alpha:
            tt_flag = "UPPERBOUND"
        elif best_score >= beta:
            tt_flag = "LOWERBOUND"
        else:
            tt_flag = "EXACT"

        # Increment mate score by depth so ie M1 is preferred over M2
        if best_score <= -MATE_SCORE: # TODO play into longest mating sequence if on losing side?
            best_score += depth

        ttable[key] = (depth, best_move, best_score, tt_flag)

        return (best_move, best_score)
        

def iterative_deepening(board, depth, movetime = INF, stop = lambda: False):
    """
    Approaches the desired search depth in steps, maintaining effiency
    with the transposition table
    """
    global nodes
    global start_time
    
    move = None
    score = -INF
    d = 0
    for d in range(1, depth + 1):
        if can_exit_search(movetime, stop, start_time):
            break

        move, score = negamax(board, d, -MATE_SCORE, MATE_SCORE, movetime, stop)

        if not can_exit_search(movetime, stop, start_time):
            stdout.write(uci_output(move, score, d, nodes, start_time))
            stdout.flush()

    # Print out info
    stdout.write(uci_output(move, score, d, nodes, start_time))
    stdout.flush()
    stdout.write("bestmove {}\n".format(move))
    stdout.flush()

    return (move, score)
    
    
def cpu_move(board, depth, movetime = INF, stop = lambda: False):
    """
    Chooses a move for the CPU
    If inside opening book make book move
    If inside Gaviota tablebase make tablebase move
    Else search for a move
    """
    global OPENING_BOOK
    global ttable
    global htable

    global nodes
    global start_time
    
    nodes = 0
    start_time = time.time_ns()

    if OPENING_BOOK:
        try:
            with chess.polyglot.open_reader(OPENING_BOOK_LOCATION) as opening_book: # https://sourceforge.net/projects/codekiddy-chess/files/
                opening = opening_book.choice(board)
                opening_book.close()
                return opening.move
        except:
            OPENING_BOOK = False

    if ENDGAME_BOOK and get_num_pieces(board) <= 5:
        evals = []
        for move in list(board.legal_moves):
            board.push(move)
            score = eval_endgame(board)
            board.pop()
            evals.append((move, score))
        move = max(evals, key = lambda eval : eval[1])[0]

        # Append to threefold repetition table
        board.push(move)
        if board._transposition_key() in rtable:
            rtable[board._transposition_key()] += 1
        board.pop()

        return move

    move = iterative_deepening(board, depth, movetime, stop)[0]

    ttable.clear()
    htable = [[[0 for x in range(64)] for y in range(64)] for z in range(2)] # Reset history heuristic table

    # Append to threefold repetition table
    board.push(move)
    if board._transposition_key() in rtable:
        rtable[board._transposition_key()] += 1
    board.pop()

    return move
