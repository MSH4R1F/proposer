'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  ChevronRight,
  ChevronDown,
  CheckCircle2,
  Circle,
  Clock,
  PanelRightClose,
  PanelRightOpen,
  Home,
  Calendar,
  PoundSterling,
  AlertCircle,
  FileText,
  Receipt,
  MessageSquare,
  ClipboardCheck,
  User,
  Sparkles,
  Copy,
  Check,
  Share2,
  Users,
} from 'lucide-react';
import type { IntakeStage, CaseFile, DisputeInfo } from '@/lib/types/chat';
import { INTAKE_STAGES, getStageIndex } from '@/lib/constants/stages';

interface IntakeSidebarProps {
  currentStage: IntakeStage;
  caseFile: CaseFile | null;
  completeness: number;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  dispute?: DisputeInfo | null;
  userRole?: string;
}

const STAGE_ICONS: Record<string, React.ReactNode> = {
  greeting: <Sparkles className="h-4 w-4" />,
  role_identification: <User className="h-4 w-4" />,
  basic_details: <Home className="h-4 w-4" />,
  tenancy_details: <Calendar className="h-4 w-4" />,
  deposit_details: <PoundSterling className="h-4 w-4" />,
  issue_identification: <AlertCircle className="h-4 w-4" />,
  evidence_collection: <FileText className="h-4 w-4" />,
  claim_amounts: <Receipt className="h-4 w-4" />,
  narrative: <MessageSquare className="h-4 w-4" />,
  confirmation: <ClipboardCheck className="h-4 w-4" />,
  complete: <CheckCircle2 className="h-4 w-4" />,
};

interface StageData {
  label: string;
  value: string | null;
}

function getStageData(stageKey: string, caseFile: CaseFile | null): StageData[] {
  if (!caseFile) return [];

  switch (stageKey) {
    case 'role_identification':
      return [
        { label: 'Role', value: caseFile.user_role ? caseFile.user_role.charAt(0).toUpperCase() + caseFile.user_role.slice(1) : null },
      ];
    case 'basic_details':
      return [
        { label: 'Address', value: caseFile.property?.address || null },
        { label: 'Postcode', value: caseFile.property?.postcode || null },
        { label: 'Type', value: caseFile.property?.property_type || null },
      ];
    case 'tenancy_details':
      return [
        { label: 'Start Date', value: caseFile.tenancy?.start_date || null },
        { label: 'End Date', value: caseFile.tenancy?.end_date || null },
        { label: 'Monthly Rent', value: caseFile.tenancy?.monthly_rent ? `£${caseFile.tenancy.monthly_rent}` : null },
      ];
    case 'deposit_details':
      return [
        { label: 'Amount', value: caseFile.tenancy?.deposit_amount ? `£${caseFile.tenancy.deposit_amount}` : null },
        { label: 'Protected', value: caseFile.tenancy?.deposit_protected !== undefined ? (caseFile.tenancy.deposit_protected ? 'Yes' : 'No') : null },
        { label: 'Scheme', value: caseFile.tenancy?.deposit_scheme || null },
      ];
    case 'issue_identification':
      return [
        { label: 'Issues', value: caseFile.issues && caseFile.issues.length > 0 ? caseFile.issues.map(i => i.replace(/_/g, ' ')).join(', ') : null },
        { label: 'Dispute Amount', value: caseFile.dispute_amount ? `£${caseFile.dispute_amount}` : null },
      ];
    case 'evidence_collection':
      return [
        { label: 'Evidence Items', value: caseFile.evidence && caseFile.evidence.length > 0 ? `${caseFile.evidence.length} item(s)` : null },
      ];
    case 'claim_amounts':
      const claims = caseFile.user_role === 'tenant' ? caseFile.tenant_claims : caseFile.landlord_claims;
      return [
        { label: 'Claims', value: claims && claims.length > 0 ? `${claims.length} claim(s)` : null },
        { label: 'Total', value: claims && claims.length > 0 ? `£${claims.reduce((sum, c) => sum + c.amount, 0)}` : null },
      ];
    case 'narrative':
      const narrative = caseFile.user_role === 'tenant' ? caseFile.tenant_narrative : caseFile.landlord_narrative;
      return [
        { label: 'Summary', value: narrative ? `${narrative.slice(0, 50)}...` : null },
      ];
    default:
      return [];
  }
}

function StageItem({
  stage,
  currentStage,
  caseFile,
  index,
}: {
  stage: typeof INTAKE_STAGES[0];
  currentStage: IntakeStage;
  caseFile: CaseFile | null;
  index: number;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const currentIndex = getStageIndex(currentStage);
  const isCompleted = index < currentIndex;
  const isCurrent = stage.key === currentStage;
  const isPending = index > currentIndex;
  
  const stageData = getStageData(stage.key, caseFile);
  const hasData = stageData.some(d => d.value !== null);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button
          className={cn(
            'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
            'hover:bg-accent/50',
            isCurrent && 'bg-primary/10 border border-primary/20',
            isCompleted && 'text-muted-foreground'
          )}
        >
          <div className={cn(
            'shrink-0',
            isCompleted && 'text-success',
            isCurrent && 'text-primary',
            isPending && 'text-muted-foreground/50'
          )}>
            {isCompleted ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : isCurrent ? (
              <Clock className="h-4 w-4" />
            ) : (
              <Circle className="h-4 w-4" />
            )}
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={cn(
                'text-sm font-medium truncate',
                isPending && 'text-muted-foreground/50'
              )}>
                {stage.label}
              </span>
            </div>
          </div>
          
          {hasData && (
            <ChevronRight className={cn(
              'h-4 w-4 shrink-0 transition-transform',
              isOpen && 'rotate-90'
            )} />
          )}
        </button>
      </CollapsibleTrigger>
      
      {hasData && (
        <CollapsibleContent>
          <div className="ml-10 mr-3 mb-2 p-2 rounded bg-muted/50 space-y-1">
            {stageData.map((data, i) => (
              data.value && (
                <div key={i} className="flex justify-between text-xs">
                  <span className="text-muted-foreground">{data.label}:</span>
                  <span className="font-medium truncate ml-2 max-w-[120px]" title={data.value}>
                    {data.value}
                  </span>
                </div>
              )
            ))}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}

export function IntakeSidebar({
  currentStage,
  caseFile,
  completeness,
  isCollapsed = false,
  onToggleCollapse,
  dispute,
  userRole,
}: IntakeSidebarProps) {
  const [copied, setCopied] = useState(false);
  
  const handleCopyCode = async () => {
    if (!dispute?.invite_code) return;
    try {
      await navigator.clipboard.writeText(dispute.invite_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleShare = async () => {
    if (!dispute?.invite_code) return;
    const shareUrl = `${window.location.origin}/chat?invite=${dispute.invite_code}`;
    const shareData = {
      title: 'Join My Deposit Dispute',
      text: `Join my deposit dispute on Proposer using code: ${dispute.invite_code}`,
      url: shareUrl,
    };

    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(
          `Join my deposit dispute on Proposer: ${shareUrl}`
        );
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch (err) {
      console.error('Failed to share:', err);
    }
  };

  const otherParty = userRole === 'tenant' ? 'landlord' : 'tenant';

  if (isCollapsed) {
    return (
      <div className="w-12 border-l bg-muted/30 flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          className="mb-4"
        >
          <PanelRightOpen className="h-4 w-4" />
        </Button>
        
        <div className="flex-1 flex flex-col items-center gap-1">
          {INTAKE_STAGES.slice(0, -1).map((stage, index) => {
            const currentIndex = getStageIndex(currentStage);
            const isCompleted = index < currentIndex;
            const isCurrent = stage.key === currentStage;
            
            return (
              <div
                key={stage.key}
                className={cn(
                  'w-2 h-2 rounded-full',
                  isCompleted && 'bg-success',
                  isCurrent && 'bg-primary',
                  !isCompleted && !isCurrent && 'bg-muted-foreground/20'
                )}
                title={stage.label}
              />
            );
          })}
        </div>
        
        <div className="mt-4 text-xs font-medium text-muted-foreground">
          {Math.round(completeness * 100)}%
        </div>
      </div>
    );
  }

  return (
    <div className="w-72 border-l bg-muted/30 flex flex-col">
      <div className="p-4 border-b flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Intake Progress</h3>
          <p className="text-xs text-muted-foreground">
            {Math.round(completeness * 100)}% complete
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onToggleCollapse}>
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>
      
      <div className="p-3">
        <div className="h-2 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${completeness * 100}%` }}
          />
        </div>
      </div>

      {/* Missing Required Information Alert */}
      {caseFile?.missing_info && caseFile.missing_info.length > 0 && (
        <div className="px-3 pb-3">
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-amber-900 dark:text-amber-100 mb-1.5">
                  Required Information Missing
                </p>
                <ul className="text-[11px] text-amber-800 dark:text-amber-200 space-y-1">
                  {caseFile.missing_info.map((item, index) => (
                    <li key={index} className="flex items-start gap-1">
                      <Circle className="h-2 w-2 fill-current shrink-0 mt-0.5" />
                      <span className="capitalize">{item}</span>
                    </li>
                  ))}
                </ul>
                <p className="text-[10px] text-amber-700 dark:text-amber-300 mt-2 italic">
                  Please provide this information to generate a prediction
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Success Message when all required fields collected */}
      {caseFile?.missing_info && caseFile.missing_info.length === 0 && completeness >= 0.7 && (
        <div className="px-3 pb-3">
          <div className="p-2.5 rounded-lg bg-success/10 border border-success/20">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-success">All Required Info Collected!</p>
                <p className="text-[10px] text-muted-foreground">
                  Ready to generate prediction
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Invite Code / Dispute Status Section */}
      {dispute && (
        <div className="px-3 pb-3 border-b">
          {dispute.has_both_parties ? (
            <div className="p-2.5 rounded-lg bg-success/10 border border-success/20">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-success shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-success">Both Parties Connected</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    The {otherParty} has joined
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-2.5 rounded-lg bg-muted border">
              <div className="flex items-center gap-2 mb-2">
                <Share2 className="h-3.5 w-3.5 text-muted-foreground" />
                <p className="text-xs font-medium">Share with {otherParty}</p>
              </div>
              <div className="flex items-center gap-1.5 mb-2">
                <div className="flex-1 px-2 py-1.5 bg-background rounded text-center">
                  <span className="font-mono text-xs font-semibold tracking-wide">
                    {dispute.invite_code}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={handleCopyCode}
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-success" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
              <Button
                variant="secondary"
                size="sm"
                className="w-full h-7 text-xs"
                onClick={handleShare}
              >
                <Share2 className="h-3 w-3 mr-1.5" />
                Share Link
              </Button>
            </div>
          )}
        </div>
      )}
      
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-1">
          {INTAKE_STAGES.slice(0, -1).map((stage, index) => (
            <StageItem
              key={stage.key}
              stage={stage}
              currentStage={currentStage}
              caseFile={caseFile}
              index={index}
            />
          ))}
        </div>
      </ScrollArea>
      
      {caseFile?.missing_info && caseFile.missing_info.length > 0 && (
        <div className="p-3 border-t">
          <p className="text-xs font-medium text-muted-foreground mb-2">Still needed:</p>
          <ul className="text-xs space-y-1">
            {caseFile.missing_info.slice(0, 3).map((item, i) => (
              <li key={i} className="flex items-center gap-2 text-muted-foreground">
                <Circle className="h-2 w-2" />
                <span className="capitalize">{item}</span>
              </li>
            ))}
            {caseFile.missing_info.length > 3 && (
              <li className="text-muted-foreground/60">
                +{caseFile.missing_info.length - 3} more
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
