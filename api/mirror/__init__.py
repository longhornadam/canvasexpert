"""CanvasMirror — a disposable local mirror of Canvas course facts.

Design laws (docs/mirror.md):
1. Canvas is truth; every mirror file is disposable and rebuildable by re-sync.
2. Sync is deterministic — no LLM anywhere in the data path.
3. Real data at rest under teacher custody (same boundary as Canvas itself);
   pseudonymization stays at the outbound MCP/LLM gate.
4. Freshness is always visible: every collection carries an envelope, and
   every mirror-served read reports synced_at + source.
5. Foreground wins: sync yields to interactive work.
"""
