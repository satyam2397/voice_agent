import type { FlashCard } from "../types";

interface Props {
  cards: FlashCard[];
}

export function FlashCardPanel({ cards }: Props) {
  return (
    <section className="panel cards-panel">
      <header className="panel-header">
        <h2>Flash cards</h2>
        {cards.length > 0 && <span className="count">{cards.length}</span>}
      </header>

      <div className="panel-body">
        {cards.length === 0 && (
          <p className="empty-state">
            Nudges appear here when the conversation warrants one. Most turns
            will not trigger a card — that is by design.
          </p>
        )}

        {cards.map((card) => (
          <article key={card.id} className="flash-card">
            <div className="card-meta">
              <span className="card-reason">{card.triggerReason}</span>
              {card.latencyMs !== null && (
                <span className="card-latency">{card.latencyMs} ms</span>
              )}
            </div>
            <p className="card-content">{card.content}</p>
            {card.toolsUsed.length > 0 && (
              <div className="card-tools">
                {card.toolsUsed.map((tool, i) => (
                  <span key={`${tool}-${i}`} className="card-tool">
                    {tool}
                  </span>
                ))}
                {card.inputTokens !== null && (
                  <span className="card-tokens">
                    {card.inputTokens}+{card.outputTokens} tok
                  </span>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
