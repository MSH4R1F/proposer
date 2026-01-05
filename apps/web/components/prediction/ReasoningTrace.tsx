'use client';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ReasoningStep } from './ReasoningStep';
import { Brain } from 'lucide-react';
import type { ReasoningStep as ReasoningStepType } from '@/lib/types/prediction';

interface ReasoningTraceProps {
  steps: ReasoningStepType[];
  totalCases?: number;
}

export function ReasoningTrace({ steps, totalCases }: ReasoningTraceProps) {
  if (!steps || steps.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Brain className="h-5 w-5" />
          Reasoning Trace
          {totalCases && (
            <span className="text-sm font-normal text-muted-foreground">
              ({totalCases} cases analyzed)
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Accordion type="single" collapsible className="w-full">
          {steps.map((step, index) => (
            <AccordionItem key={`step-${index}`} value={`step-${index}`}>
              <AccordionTrigger className="text-left">
                <div className="flex items-center gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground shrink-0">
                    {step.step_number}
                  </span>
                  <span className="font-medium">{step.title}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <ReasoningStep step={step} className="pt-2" />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CardContent>
    </Card>
  );
}
