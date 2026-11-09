# Offline learning package

CQL / IQL with constraint critics, fitted-Q evaluation, weighted
importance sampling, and the safe-improvement acceptance test
(Sections 10.3--10.4).

New datasets must include behavior-policy probabilities and provenance
metadata before WIS or final policy claims. `offline/ope.py` provides WIS
with effective sample size and optional bootstrap intervals, plus action
support diagnostics, and a transparent linear FQE baseline. These are
uncertainty estimates, not safety guarantees; validate them against true
emulator returns before using them for acceptance decisions.
