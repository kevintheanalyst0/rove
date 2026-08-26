"""EATP-031: the accumulated inbox. Every job that ever cleared the quality
gate stays here — across runs, across days — until Kevin applies or
dismisses it. Fixes the "I didn't check yesterday so I lost yesterday's
matches" gap left by RESULTS_FILE being overwritten every run.
"""
