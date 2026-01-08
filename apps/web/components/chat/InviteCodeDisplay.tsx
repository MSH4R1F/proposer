'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Copy, Check, Share2, Users } from 'lucide-react';
import type { DisputeInfo } from '@/lib/types/chat';

interface InviteCodeDisplayProps {
  dispute: DisputeInfo;
  userRole: string;
}

export function InviteCodeDisplay({ dispute, userRole }: InviteCodeDisplayProps) {
  const [copied, setCopied] = useState(false);
  
  const otherParty = userRole === 'tenant' ? 'landlord' : 'tenant';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(dispute.invite_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleShare = async () => {
    const shareData = {
      title: 'Join My Deposit Dispute',
      text: `Join my deposit dispute on Proposer using code: ${dispute.invite_code}`,
      url: `${window.location.origin}/chat?invite=${dispute.invite_code}`,
    };

    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(
          `Join my deposit dispute on Proposer using code: ${dispute.invite_code}\n${shareData.url}`
        );
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch (err) {
      console.error('Failed to share:', err);
    }
  };

  if (dispute.has_both_parties) {
    return (
      <Card className="border-success/20 bg-success/5">
        <CardContent className="pt-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-success/10">
              <Users className="h-5 w-5 text-success" />
            </div>
            <div>
              <p className="font-medium text-success">Both Parties Connected</p>
              <p className="text-sm text-muted-foreground">
                The {otherParty} has joined this dispute
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Share2 className="h-4 w-4" />
          Share with {otherParty}
        </CardTitle>
        <CardDescription>
          Give this code to the {otherParty} so they can join this dispute
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="flex-1 p-3 bg-muted rounded-lg text-center">
            <span className="font-mono text-lg font-semibold tracking-wider">
              {dispute.invite_code}
            </span>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={handleCopy}
            className="shrink-0"
          >
            {copied ? (
              <Check className="h-4 w-4 text-success" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>
        
        <Button
          variant="secondary"
          className="w-full"
          onClick={handleShare}
        >
          <Share2 className="h-4 w-4 mr-2" />
          Share Invite Link
        </Button>
        
        {dispute.waiting_message && (
          <p className="text-sm text-muted-foreground text-center">
            {dispute.waiting_message}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
