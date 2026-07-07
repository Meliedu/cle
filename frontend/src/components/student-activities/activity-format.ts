import type {
  Activity,
  ActivityConfig,
  ActivityResponsePayload,
} from "@/hooks/use-activities";

/**
 * Narrowing helpers over the loosely-typed activity `config` / response
 * `payload` shapes (backend B8/B9). The wire types are unions that include a
 * permissive `Record<string, unknown>` arm, so the student flows read them
 * defensively rather than trusting a discriminant. Pure functions — no React.
 */

/** The ordered swipe prompts for a `swipe` activity (empty when malformed). */
export function swipePrompts(config: ActivityConfig): readonly string[] {
  const value = (config as Record<string, unknown>).prompts;
  return Array.isArray(value) ? value.filter(isNonEmptyString) : [];
}

/** The selectable options for a `vote` activity (empty when malformed). */
export function voteOptions(config: ActivityConfig): readonly string[] {
  const value = (config as Record<string, unknown>).options;
  return Array.isArray(value) ? value.filter(isNonEmptyString) : [];
}

/** The available reactions for a `comment_reaction` activity. */
export function commentReactions(config: ActivityConfig): readonly string[] {
  const value = (config as Record<string, unknown>).reactions;
  return Array.isArray(value) ? value.filter(isNonEmptyString) : [];
}

/** One stacked `comment_reaction` entry as persisted by the server. */
export interface ReactionEntry {
  readonly reaction: string;
}

/**
 * The stacked reaction entries inside a `comment_reaction` response payload
 * (`{entries: [{reaction}, …]}`, backend `_merge_payload`). Tolerates a legacy
 * single `{reaction}` shape and an absent payload.
 */
export function reactionEntries(
  payload: ActivityResponsePayload | null | undefined
): readonly ReactionEntry[] {
  if (!payload) return [];
  const record = payload as Record<string, unknown>;
  const entries = record.entries;
  if (Array.isArray(entries)) {
    return entries
      .map((entry) => {
        const reaction = (entry as Record<string, unknown>)?.reaction;
        return isNonEmptyString(reaction) ? { reaction } : null;
      })
      .filter((entry): entry is ReactionEntry => entry !== null);
  }
  if (isNonEmptyString(record.reaction)) return [{ reaction: record.reaction }];
  return [];
}

/** An activity accepts responses only while `published` or `live` (backend B9). */
export function isActivityOpen(activity: Activity): boolean {
  return activity.status === "published" || activity.status === "live";
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}
