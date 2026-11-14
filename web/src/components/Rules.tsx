import { formatRuleValue } from "../format";
import type { RuleUsage } from "../types";

function usageRatio(rule: RuleUsage): number | null {
  if (rule.used === null || rule.kind === "min" || rule.limit <= 0) return null;
  return Math.min(rule.used / rule.limit, 1);
}

function describe(rule: RuleUsage): string {
  const limit = formatRuleValue(rule.limit, rule.unit);
  if (rule.used === null) return `no data yet (${rule.kind === "min" ? "floor" : "limit"} ${limit})`;
  const used = formatRuleValue(rule.used, rule.unit);
  return rule.kind === "min" ? `${used} (floor ${limit})` : `${used} of ${limit}`;
}

export function Rules({ rules }: { rules: RuleUsage[] }) {
  return (
    <section className="card">
      <h2>Active rules</h2>
      <ul className="rules">
        {rules.map((rule) => {
          const ratio = usageRatio(rule);
          return (
            <li key={rule.id}>
              <div className="rule-head">
                <span>{rule.label}</span>
                <span className={rule.breached ? "down" : "muted"}>{describe(rule)}</span>
              </div>
              {ratio !== null && (
                <div className="meter" aria-hidden="true">
                  <span className={rule.breached ? "meter-fill meter-breached" : "meter-fill"} style={{ width: `${ratio * 100}%` }} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
