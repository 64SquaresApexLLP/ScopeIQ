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
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED';
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

export interface SiteDetail {
  site: Row;
  actions: WorkflowAction[];
  milestones: Row[];
  documents: Row[];
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
