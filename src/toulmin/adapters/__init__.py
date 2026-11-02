"""L3 adapters: run one headless, read-only model session per call.

Adapters know command lines and output formats; everything about what a review is
lives in L2 and the role files. Flags were checked against Claude Code 2.1.316 and
Codex CLI 0.166.0 on 2026-11-02 and will drift; see each module.
"""
