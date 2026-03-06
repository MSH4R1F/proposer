'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, Clock, PoundSterling, ExternalLink, Lock, FileX } from 'lucide-react';

export function EscalationOptions() {
  return (
    <div className="space-y-4">
      {/* Main escalation card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">First-tier Tribunal (Property Chamber)</CardTitle>
          <p className="text-sm text-muted-foreground">
            If mediation has been unsuccessful, you may escalate your dispute to the First-tier
            Tribunal (Property Chamber) — an independent government body that adjudicates tenancy
            deposit disputes.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Process steps */}
          <div>
            <h3 className="text-sm font-semibold mb-3">Process Overview</h3>
            <ol className="space-y-2 text-sm text-muted-foreground list-decimal list-inside">
              <li>Submit a formal application to the tribunal with supporting evidence.</li>
              <li>Both parties are notified and given opportunity to respond.</li>
              <li>A hearing is scheduled (in person or by written submissions).</li>
              <li>A judge reviews the evidence and issues a legally binding decision.</li>
            </ol>
          </div>

          {/* Timeline & Costs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-muted/50 border border-border/50">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Timeline</span>
              </div>
              <p className="text-2xl font-bold">6–12</p>
              <p className="text-sm text-muted-foreground">months on average</p>
            </div>

            <div className="p-4 rounded-lg bg-muted/50 border border-border/50">
              <div className="flex items-center gap-2 mb-2">
                <PoundSterling className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Costs</span>
              </div>
              <div className="space-y-1">
                <p className="text-sm">
                  <span className="font-medium">Tenant:</span>{' '}
                  <span className="text-green-600 font-semibold">£0</span>
                </p>
                <p className="text-sm">
                  <span className="font-medium">Landlord:</span>{' '}
                  <span className="font-semibold">£200–£500</span>
                </p>
              </div>
            </div>
          </div>

          {/* ADR link */}
          <div className="p-4 rounded-lg bg-primary/5 border border-primary/10">
            <h3 className="text-sm font-semibold mb-2">Alternative: Free Deposit Scheme ADR</h3>
            <p className="text-sm text-muted-foreground mb-3">
              If your deposit is protected with TDS or DPS, you may use their free Alternative
              Dispute Resolution (ADR) service — often faster than tribunal.
            </p>
            <a
              href="https://www.tenancydepositscheme.com/dispute-resolution/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              TDS Dispute Resolution
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </CardContent>
      </Card>

      {/* Confidentiality disclaimer */}
      <div className="relative overflow-hidden rounded-xl p-4 bg-blue-500/5 border border-blue-500/20">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500/50 via-blue-500 to-blue-500/50" />
        <div className="flex items-start gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-blue-500/10">
            <Lock className="h-5 w-5 text-blue-500" />
          </div>
          <div>
            <h4 className="font-semibold text-sm text-blue-600 mb-1">Confidentiality</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              All content from this mediation process is confidential within this process and{' '}
              <strong className="text-foreground">
                cannot be referred to in later legal proceedings
              </strong>
              .
            </p>
          </div>
        </div>
      </div>

      {/* AI admissibility disclaimer */}
      <div className="relative overflow-hidden rounded-xl p-4 bg-warning/5 border border-warning/20">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-warning/50 via-warning to-warning/50" />
        <div className="flex items-start gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-warning/10">
            <FileX className="h-5 w-5 text-warning" />
          </div>
          <div>
            <h4 className="font-semibold text-sm text-warning mb-1">AI Analysis Notice</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              This AI analysis is{' '}
              <strong className="text-foreground">not court-admissible</strong> and does not
              constitute legal advice. It is provided for informational purposes only. Always
              consult a qualified solicitor before commencing tribunal proceedings.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
