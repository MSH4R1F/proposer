import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ThumbsUp, ThumbsDown, AlertCircle, CheckCircle2, XCircle, HelpCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StrengthsWeaknessesProps {
  strengths: string[];
  weaknesses: string[];
  uncertainties?: string[];
}

export function StrengthsWeaknesses({
  strengths,
  weaknesses,
  uncertainties,
}: StrengthsWeaknessesProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Strengths Card */}
      <Card className="border-0 shadow-soft overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-emerald-500 to-teal-500" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-3 text-lg">
            <div className="p-2 rounded-lg bg-emerald-500/10">
              <ThumbsUp className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <span className="text-emerald-700 dark:text-emerald-300">Strengths</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {strengths && strengths.length > 0 ? (
            <ul className="space-y-3">
              {strengths.map((strength, index) => (
                <li
                  key={index}
                  className="flex items-start gap-3 text-sm"
                >
                  <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />
                  <span className="text-muted-foreground leading-relaxed">{strength}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground italic">
              No specific strengths identified
            </p>
          )}
        </CardContent>
      </Card>

      {/* Weaknesses Card */}
      <Card className="border-0 shadow-soft overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-red-500 to-rose-500" />
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-3 text-lg">
            <div className="p-2 rounded-lg bg-red-500/10">
              <ThumbsDown className="h-5 w-5 text-red-600 dark:text-red-400" />
            </div>
            <span className="text-red-700 dark:text-red-300">Weaknesses</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {weaknesses && weaknesses.length > 0 ? (
            <ul className="space-y-3">
              {weaknesses.map((weakness, index) => (
                <li
                  key={index}
                  className="flex items-start gap-3 text-sm"
                >
                  <XCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                  <span className="text-muted-foreground leading-relaxed">{weakness}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground italic">
              No specific weaknesses identified
            </p>
          )}
        </CardContent>
      </Card>

      {/* Uncertainties Card */}
      {uncertainties && uncertainties.length > 0 && (
        <Card className="md:col-span-2 border-0 shadow-soft overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-amber-500 to-yellow-500" />
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-3 text-lg">
              <div className="p-2 rounded-lg bg-amber-500/10">
                <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              </div>
              <span className="text-amber-700 dark:text-amber-300">Uncertainties</span>
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              These factors may affect the final outcome
            </p>
          </CardHeader>
          <CardContent>
            <ul className="grid sm:grid-cols-2 gap-3">
              {uncertainties.map((uncertainty, index) => (
                <li
                  key={index}
                  className="flex items-start gap-3 text-sm p-3 rounded-lg bg-amber-500/5 border border-amber-500/10"
                >
                  <HelpCircle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                  <span className="text-muted-foreground leading-relaxed">{uncertainty}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
