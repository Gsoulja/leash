# LEASH-006: Shop-text reader (regex MVP, Laya after MVP)

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~54 h (13 tickets; ~10 h in the MVP)
**Updated**: 2026-09-23

## Description
The deterministic regex reader and its fallback wrapper are MVP. The Laya training pipeline and in-engine adapter come after the MVP (DEC-020).

## Business Value
Reads untrusted shop text better than regex, which is our model-based differentiator, without ever deciding a verdict.

## Reference
Design: solution/docs/laya-training-pipeline.html.

## Sub-tasks
- [ ] LEASH-070 (006-T1) [M1]: Question bank v1 · S
- [ ] LEASH-071 (006-T2) [M1]: Regex fact reader · M
- [ ] LEASH-072 (006-T3) [M2]: Timeout, fallback and circuit breaker for readers · M
- [ ] LEASH-073 (006-T4) [M6]: Data factory · L
- [ ] LEASH-074 (006-T5) [M6]: Public data ingest · M
- [ ] LEASH-075 (006-T6) [M6]: Splits by family and frozen eval sets · M
- [ ] LEASH-076 (006-T7) [M6]: Regex baseline on eval sets · S
- [ ] LEASH-077 (006-T8) [M6]: RLCD fine-tune on one GPU · L
- [ ] LEASH-078 (006-T9) [M6]: Calibration · S
- [ ] LEASH-079 (006-T10) [M6]: Ask head with cost table · M
- [ ] LEASH-080 (006-T11) [M6]: Adversarial loop · M
- [ ] LEASH-081 (006-T12) [M6]: Release gate and model registry · M
- [ ] LEASH-082 (006-T13) [M6]: Laya reader adapter in the engine · M

## Done when
Every sub-task is in `done/`.
