import type { IntakeStage } from '@/lib/types/chat';

export interface StageInfo {
  key: IntakeStage;
  label: string;
  description: string;
  step: number;
}

export const INTAKE_STAGES: StageInfo[] = [
  {
    key: 'greeting',
    label: 'Welcome',
    description: 'Introduction and role selection',
    step: 1,
  },
  {
    key: 'role_identification',
    label: 'Role',
    description: 'Confirm your role',
    step: 2,
  },
  {
    key: 'basic_details',
    label: 'Property',
    description: 'Property address and type',
    step: 3,
  },
  {
    key: 'tenancy_details',
    label: 'Tenancy',
    description: 'Dates, rent, and agreement',
    step: 4,
  },
  {
    key: 'deposit_details',
    label: 'Deposit',
    description: 'Amount and protection status',
    step: 5,
  },
  {
    key: 'issue_identification',
    label: 'Issues',
    description: 'What is being disputed',
    step: 6,
  },
  {
    key: 'evidence_collection',
    label: 'Evidence',
    description: 'Supporting documents',
    step: 7,
  },
  {
    key: 'claim_amounts',
    label: 'Claims',
    description: 'Specific amounts claimed',
    step: 8,
  },
  {
    key: 'narrative',
    label: 'Summary',
    description: 'Your full account',
    step: 9,
  },
  {
    key: 'confirmation',
    label: 'Confirm',
    description: 'Review and confirm',
    step: 10,
  },
  {
    key: 'complete',
    label: 'Complete',
    description: 'Ready for prediction',
    step: 11,
  },
];

export function getStageIndex(stage: IntakeStage): number {
  const index = INTAKE_STAGES.findIndex((s) => s.key === stage);
  return index === -1 ? 0 : index;
}

export function getStageInfo(stage: IntakeStage): StageInfo | undefined {
  return INTAKE_STAGES.find((s) => s.key === stage);
}

export function getStageLabel(stage: IntakeStage): string {
  const found = INTAKE_STAGES.find((s) => s.key === stage);
  return found?.label || 'Unknown';
}

export function getStageProgress(stage: IntakeStage): number {
  const index = getStageIndex(stage);
  return Math.round((index / (INTAKE_STAGES.length - 1)) * 100);
}

export function isStageComplete(
  currentStage: IntakeStage,
  targetStage: IntakeStage
): boolean {
  return getStageIndex(currentStage) > getStageIndex(targetStage);
}
