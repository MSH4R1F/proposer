import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ThumbsUp, ThumbsDown, AlertCircle } from 'lucide-react';

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
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-lg text-green-600">
            <ThumbsUp className="h-5 w-5" />
            Strengths
          </CardTitle>
        </CardHeader>
        <CardContent>
          {strengths && strengths.length > 0 ? (
            <ul className="space-y-2">
              {strengths.map((strength, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-green-500 shrink-0" />
                  {strength}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No specific strengths identified
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-lg text-red-600">
            <ThumbsDown className="h-5 w-5" />
            Weaknesses
          </CardTitle>
        </CardHeader>
        <CardContent>
          {weaknesses && weaknesses.length > 0 ? (
            <ul className="space-y-2">
              {weaknesses.map((weakness, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
                  {weakness}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No specific weaknesses identified
            </p>
          )}
        </CardContent>
      </Card>

      {uncertainties && uncertainties.length > 0 && (
        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-lg text-yellow-600">
              <AlertCircle className="h-5 w-5" />
              Uncertainties
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {uncertainties.map((uncertainty, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-yellow-500 shrink-0" />
                  {uncertainty}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
