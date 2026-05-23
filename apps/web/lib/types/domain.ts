/**
 * SHA-20 Phase 9: domain routing types and user-facing matter labels.
 *
 * The frontend NEVER renders raw domain ids (e.g. "housing.deposit.v1").
 * It always renders the plain-English matter label produced by
 * `matterLabelFor()` below. The label map mirrors
 * `packages/llm_orchestrator/routing/domain_router.py:USER_FACING_MATTER_LABELS`.
 *
 * Forum and source-kind labels are rendered next to citations to give
 * users a quick visual cue (Property Chamber vs Housing Ombudsman vs
 * Statute) without exposing the legal-taxonomy enum values.
 */

export type RoutingOutcome = 'route' | 'clarify' | 'unsupported' | 'abstain';

export interface RoutingMetadata {
  outcome: RoutingOutcome;
  domain_id?: string | null;
  matter_label?: string | null;
  candidate_domains?: string[];
  candidate_matter_labels?: string[];
  clarifier_text?: string | null;
  confidence?: number | null;
  margin?: number | null;
  reason?: string | null;
  capture_in?: 'research' | 'log_only' | null;
  metadata?: Record<string, unknown>;
}

export interface RouteResponse {
  routing: RoutingMetadata;
}

// Plain-English matter labels. Keep in sync with the Python router.
export const MATTER_LABELS: Record<string, string> = {
  'housing.deposit.v1': 'Deposit deductions',
  'housing.repairs_social.v1': 'Repairs, damp, mould, or safety',
  'housing.property_chamber.rro.v1': 'Rent repayment order issue',
  'employment.unfair_dismissal.v1': 'Work dismissal issue',
};

export function matterLabelFor(domainId?: string | null): string {
  if (!domainId) return 'Legal matter';
  return MATTER_LABELS[domainId] ?? 'Legal matter';
}

// Forum + source-kind labels for citation cards. Internal enum names
// like "first_tier_tribunal_property_chamber" never reach the UI.
export const FORUM_LABELS: Record<string, string> = {
  property_chamber: 'Property Chamber',
  first_tier_tribunal_property_chamber: 'Property Chamber',
  housing_ombudsman: 'Housing Ombudsman',
  county_court: 'County Court',
  deposit_scheme_adjudication: 'Deposit scheme adjudication',
  employment_tribunal: 'Employment Tribunal',
  employment_appeal_tribunal: 'Employment Appeal Tribunal',
  upper_tribunal: 'Upper Tribunal',
};

export function forumLabelFor(forum?: string | null): string | null {
  if (!forum) return null;
  return FORUM_LABELS[forum] ?? forum.replace(/_/g, ' ');
}

export const SOURCE_KIND_LABELS: Record<string, string> = {
  tribunal_decision: 'Tribunal decision',
  ombudsman_decision: 'Ombudsman decision',
  statute: 'Statute',
  statutory_instrument: 'Statutory instrument',
  guidance: 'Official guidance',
  case_summary: 'Case summary',
};

export function sourceKindLabelFor(kind?: string | null): string | null {
  if (!kind) return null;
  return SOURCE_KIND_LABELS[kind] ?? kind.replace(/_/g, ' ');
}

// SHA domain catalog types — returned by GET /domains
export type DomainAvailability = 'live' | 'research_beta' | 'coming_soon';

export interface PartyRoleOption {
  value: string;
  label: string;
  blurb?: string;
}

export interface DomainCatalogItem {
  id: string;
  user_facing_name: string;
  family: string;
  stage: string;
  availability: DomainAvailability;
  party_roles: PartyRoleOption[];
  intake_modes: ('guided' | 'bulk')[];
  matter_types: string[];
  disclaimer_level: 'standard' | 'research';
}
