export type TraceStepKind = 'model_turn' | 'tool_call' | 'tool_error' | 'termination';

export type TraceTerminationReason = 'end_turn' | 'max_turns' | 'model_error';

export interface TraceStep {
  index: number;
  kind: TraceStepKind;
  name?: string;
  started_at: string; // ISO 8601
  duration_ms: number;
  tokens_in?: number;
  tokens_out?: number;
  input_preview?: string;
  output_preview?: string;
  is_error: boolean;
}

export interface TraceSummary {
  trace_id: string;
  termination: TraceTerminationReason;
  total_duration_ms: number;
  total_tokens_in: number;
  total_tokens_out: number;
  steps: TraceStep[];
}
