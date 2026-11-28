"""Talon's training rules that both apps need (plan 3b): the plan file, the weekly schedule, the facts and whether a
workout counts (WD4.1). Talon works out its screens from them, and Ambrosia which days had a finished workout that
counts, for the water it adds (apps/diet/docs/plan.md AM12.4). They lived in gym/rules until 2026-11-28 and moved
here unchanged, so both apps read Talon's rows the same way.

Pure logic: no screen, database, network or clock. "today" is always passed in.
"""
