'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Plus, Link2, ArrowRight, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

interface DisputeEntrySelectorProps {
  onStartNew: () => void;
  onJoinExisting: (inviteCode: string) => void;
  onValidateCode: (code: string) => Promise<{
    valid: boolean;
    expected_role?: string;
    property_address?: string;
    message: string;
  }>;
  isLoading?: boolean;
}

export function DisputeEntrySelector({
  onStartNew,
  onJoinExisting,
  onValidateCode,
  isLoading = false,
}: DisputeEntrySelectorProps) {
  const [mode, setMode] = useState<'select' | 'join'>('select');
  const [inviteCode, setInviteCode] = useState('');
  const [validationState, setValidationState] = useState<{
    status: 'idle' | 'validating' | 'valid' | 'invalid';
    message?: string;
    expectedRole?: string;
    propertyAddress?: string;
  }>({ status: 'idle' });

  const handleValidateCode = async () => {
    if (!inviteCode.trim()) return;
    
    setValidationState({ status: 'validating' });
    const result = await onValidateCode(inviteCode.trim());
    
    if (result.valid) {
      setValidationState({
        status: 'valid',
        message: result.message,
        expectedRole: result.expected_role,
        propertyAddress: result.property_address,
      });
    } else {
      setValidationState({
        status: 'invalid',
        message: result.message,
      });
    }
  };

  const handleJoin = () => {
    if (validationState.status === 'valid') {
      onJoinExisting(inviteCode.trim());
    }
  };

  if (mode === 'join') {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="h-5 w-5" />
            Join Existing Dispute
          </CardTitle>
          <CardDescription>
            Enter the invite code shared by the other party
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Input
              placeholder="e.g. BLUE-TIGER-42"
              value={inviteCode}
              onChange={(e) => {
                setInviteCode(e.target.value.toUpperCase());
                setValidationState({ status: 'idle' });
              }}
              className="text-center text-lg font-mono tracking-wider"
              disabled={isLoading}
            />
            
            {validationState.status === 'validating' && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Validating code...
              </div>
            )}
            
            {validationState.status === 'valid' && (
              <div className="p-3 rounded-lg bg-success/10 border border-success/20 space-y-1">
                <div className="flex items-center gap-2 text-sm text-success font-medium">
                  <CheckCircle2 className="h-4 w-4" />
                  Valid code
                </div>
                {validationState.expectedRole && (
                  <p className="text-sm text-muted-foreground">
                    You will join as: <span className="font-medium capitalize">{validationState.expectedRole}</span>
                  </p>
                )}
                {validationState.propertyAddress && (
                  <p className="text-sm text-muted-foreground">
                    Property: {validationState.propertyAddress}
                  </p>
                )}
              </div>
            )}
            
            {validationState.status === 'invalid' && (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <XCircle className="h-4 w-4" />
                {validationState.message}
              </div>
            )}
          </div>
          
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setMode('select')}
              disabled={isLoading}
              className="flex-1"
            >
              Back
            </Button>
            
            {validationState.status !== 'valid' ? (
              <Button
                onClick={handleValidateCode}
                disabled={!inviteCode.trim() || validationState.status === 'validating' || isLoading}
                className="flex-1"
              >
                {validationState.status === 'validating' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  'Validate Code'
                )}
              </Button>
            ) : (
              <Button
                onClick={handleJoin}
                disabled={isLoading}
                className="flex-1"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    Join Dispute
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </>
                )}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">Welcome to Proposer</h1>
        <p className="text-muted-foreground">
          Get AI-powered guidance on your tenancy deposit dispute
        </p>
      </div>
      
      <div className="grid md:grid-cols-2 gap-4">
        <Card 
          className="cursor-pointer transition-all hover:border-primary hover:shadow-md"
          onClick={onStartNew}
        >
          <CardHeader>
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
              <Plus className="h-5 w-5 text-primary" />
            </div>
            <CardTitle className="text-lg">Start New Dispute</CardTitle>
            <CardDescription>
              Begin the intake process and get an invite code to share with the other party
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button className="w-full" disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  Get Started
                  <ArrowRight className="h-4 w-4 ml-2" />
                </>
              )}
            </Button>
          </CardContent>
        </Card>
        
        <Card 
          className="cursor-pointer transition-all hover:border-primary hover:shadow-md"
          onClick={() => setMode('join')}
        >
          <CardHeader>
            <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center mb-2">
              <Link2 className="h-5 w-5 text-secondary-foreground" />
            </div>
            <CardTitle className="text-lg">Join Existing Dispute</CardTitle>
            <CardDescription>
              Have an invite code? Enter it to join a dispute started by the other party
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" className="w-full" disabled={isLoading}>
              Enter Invite Code
              <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
