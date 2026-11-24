// Row shapes returned by the API (column names as in the database).
export type Row = Record<string, any>;

export interface User {
  user_id: string;
  name: string;
  role: string;
  organisation: string;
  service_provider?: string;
  persona?: string;
  key_screens?: string;
}

export interface WorkflowAction {
  action: string;
  to_state: string;
  requires_reason: boolean;
  requires_comment: boolean;
  description: string;
  roles: string[];
}

export interface ReasonCode {
  REASON_CODE: string;
  CATEGORY: string;
  DESCRIPTION: string;
  FAULT_PARTY: string;
  APPLIES_TO: string;
}

/** One phase of a pipeline run (or of an "implement changes" job), updated by the backend while it runs. */
export interface PipelineStep {
  key: string;
  label: string;
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'SKIPPED';
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  message: string;
  counts: Record<string, any>;
}

export interface PipelineRun {
  RUN_ID: string;
  SITE_ID: string;
  STARTED_AT: string;
  FINISHED_AT: string | null;
  STATUS: 'RUNNING' | 'SUCCEEDED' | 'SUCCEEDED_WITH_WARNINGS' | 'FAILED';
  TRIGGERED_BY: string | null;
  STEPS: PipelineStep[] | Record<string, string> | null;   // runs recorded before step tracking have a plain object
  SUMMARY: Row | null;
  WARNINGS: string[] | null;
}

export interface RevisionChange {
  redline_id: string;
  disc_id: string;
  rule_id: string;
  sheet: string;
  markup: string;
  status: string;
  applied: boolean;
  detail: string;
}

export interface RevisionCheckType {
  doc_type: string;
  picked_file: string | null;
  picked_revision: string | null;
  picked_format: string | null;
  has_superseded: boolean;
  superseded_revisions: string[];
  total_files: number;
}

export interface RevisionCheck {
  status: string;
  message: string;
  latest_picked_count: number;
  superseded_count: number;
  total_documents: number;
  types: RevisionCheckType[];
}

export interface SiteDetail {
  site: Row;
  actions: WorkflowAction[];
  milestones: Row[];
  documents: Row[];
  revision_check?: RevisionCheck;
  sectors: Row[];
  trunks: Row[];
  analyses: Row[];
  delta: Row[];
  requirements: Row[];
  estimate: Row[];
  ehs_alerts: Row[];
  last_run: Row[];
  workflow_history: Row[];
}

export interface SpQuote {
  QUOTE_ID: string;
  SITE_ID: string;
  SP_NAME: string;
  QUOTE_AMOUNT: number;
  BASELINE_AMOUNT: number;
  VARIANCE_AMOUNT: number;
  VARIANCE_PCT: number;
  STATUS: string;
  NOTES: string;
  BREAKDOWN: any[];
  SUBMITTED_BY: string;
  SUBMITTED_AT: string;
}

export interface HandshakeSummary {
  site_id: string;
  site_name: string;
  market: string;
  cx_sp: string;
  workflow_state: string;
  state_description?: string | null;      // from the workflow reference
  package_out: boolean;                   // the package has left the scoping team (with the SP, or approved)
  current_bom_rev?: string;
  is_fba_locked: boolean;
  workflow_actions: WorkflowAction[];     // the steps this user's role can take from this state
  has_bom?: boolean;
  has_run_pipeline?: boolean;
  delta: Row[];
  cd_documents?: Row[];
  bom_lines?: Row[];
  bom_summary: null | {
    lines_count: number;
    install_count: number;
    remove_count: number;
    total_material_cost: number;
    revision: string;
    file_name: string;
    is_locked: boolean;
  };
  workflow_history: Row[];
}

/** What a service provider is given for a site. */
export interface ProviderView {
  site_id: string;
  site_name?: string;
  drawings: { DOC_ID: string; FILE_NAME: string; FILE_FORMAT?: string; REVISION?: string; SIZE_BYTES?: number }[];
  requests: { when?: string; reason?: string; comment?: string }[];
  phase: 'PENDING' | 'REVIEW' | 'AGREED' | 'APPROVED';
  scope: { released: boolean; items: { SECTOR?: string; POSITION?: string; KIND?: string; CATALOG_KEY?: string; ACTION?: string; FROM_POSITION?: string }[] };
  bom: { released: boolean; approved: boolean; lines: { SECTOR?: string; CATEGORY?: string; MANUFACTURER?: string; MODEL?: string; DESCRIPTION?: string; UOM?: string; TOTAL_QTY?: number; ACTION?: string; SUPPLY?: string }[] };
}
