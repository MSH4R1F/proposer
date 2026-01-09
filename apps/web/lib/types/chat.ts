export type IntakeStage =
  | 'greeting'
  | 'role_identification'
  | 'basic_details'
  | 'tenancy_details'
  | 'deposit_details'
  | 'issue_identification'
  | 'evidence_collection'
  | 'claim_amounts'
  | 'narrative'
  | 'confirmation'
  | 'complete';

export type PartyRole = 'tenant' | 'landlord';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface PropertyDetails {
  address?: string;
  postcode?: string;
  property_type?: string;
  num_bedrooms?: number;
  furnished?: boolean;
  region?: string;
}

export interface TenancyDetails {
  start_date?: string;
  end_date?: string;
  tenancy_type?: string;
  monthly_rent?: number;
  deposit_amount?: number;
  deposit_protected?: boolean;
  deposit_scheme?: string;
  protection_date?: string;
  prescribed_info_provided?: boolean;
}

export interface EvidenceItem {
  id: string;
  type: string;
  description: string;
  file_url?: string;
  file_name?: string;
  file_type?: string;
  extracted_text?: string;
  image_description?: string;
  date_created?: string;
  confidence: number;
  source: string;
}

export interface ClaimedAmount {
  id: string;
  issue: string;
  amount: number;
  description: string;
  evidence_ids: string[];
  confidence: number;
}

export interface CaseFile {
  case_id: string;
  user_role?: PartyRole;
  created_at?: string;
  updated_at?: string;
  tenant_name?: string;
  landlord_name?: string;
  agent_name?: string;
  multiple_tenants?: boolean;
  num_tenants?: number;
  property?: PropertyDetails;
  tenancy?: TenancyDetails;
  issues?: string[];
  dispute_amount?: number;
  tenant_claims?: ClaimedAmount[];
  landlord_claims?: ClaimedAmount[];
  evidence?: EvidenceItem[];
  tenant_narrative?: string;
  landlord_narrative?: string;
  intake_complete?: boolean;
  completeness_score?: number;
  missing_info?: string[];
}

export interface DisputeInfo {
  dispute_id: string;
  invite_code: string;
  status: string;
  has_both_parties: boolean;
  is_ready_for_prediction: boolean;
  waiting_message?: string;
}

export interface ChatState {
  sessionId: string | null;
  messages: Message[];
  stage: IntakeStage;
  completeness: number;
  isLoading: boolean;
  error: string | null;
  roleSelected: boolean;
  caseFile: CaseFile | null;
  dispute: DisputeInfo | null;
}

export interface StartSessionResponse {
  session_id: string;
  response: string;
  stage: string;
  completeness: number;
  is_complete: boolean;
  case_file: CaseFile;
  role_set: boolean;
  dispute?: DisputeInfo;
}

export interface SetRoleResponse {
  session_id: string;
  response: string;
  stage: string;
  completeness: number;
  is_complete: boolean;
  case_file: CaseFile;
  role_set: boolean;
}

export interface ChatMessageResponse {
  session_id: string;
  response: string;
  stage: string;
  completeness: number;
  is_complete: boolean;
  case_file: CaseFile;
  suggested_actions?: string[];
  dispute?: DisputeInfo;  // CRITICAL: Updated dispute status for multi-party prediction
}

export interface SessionMessageData {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
}

export interface SessionStateResponse {
  session_id: string;
  stage: string;
  completeness: number;
  is_complete: boolean;
  message_count: number;
  case_file: CaseFile;
  messages: SessionMessageData[];
  dispute?: DisputeInfo;
}

export interface ValidateInviteResponse {
  valid: boolean;
  dispute_id?: string;
  created_by_role?: string;
  expected_role?: string;
  property_address?: string;
  message: string;
}

export interface JoinDisputeResponse {
  success: boolean;
  dispute_id?: string;
  status?: string;
  message: string;
}
