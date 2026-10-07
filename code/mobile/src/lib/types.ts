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
