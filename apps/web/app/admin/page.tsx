'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { 
  Users, 
  FileText, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  RefreshCw,
  Eye,
  Home,
} from 'lucide-react';
import Link from 'next/link';

interface DisputeListItem {
  dispute_id: string;
  invite_code: string;
  status: string;
  created_at: string;
  property_address: string | null;
  has_tenant: boolean;
  has_landlord: boolean;
}

interface SessionItem {
  session_id: string;
  case_id: string;
  stage: string;
  is_complete: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getStatusBadgeVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status.includes('complete') || status === 'ready_for_mediation') return 'default';
  if (status.includes('waiting')) return 'secondary';
  if (status.includes('progress')) return 'outline';
  return 'secondary';
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export default function AdminDashboard() {
  const [disputes, setDisputes] = useState<DisputeListItem[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const [disputesRes, sessionsRes] = await Promise.all([
        fetch(`${API_URL}/disputes/`),
        fetch(`${API_URL}/chat/sessions`),
      ]);
      
      if (!disputesRes.ok || !sessionsRes.ok) {
        throw new Error('Failed to fetch data');
      }
      
      const disputesData = await disputesRes.json();
      const sessionsData = await sessionsRes.json();
      
      setDisputes(disputesData);
      setSessions(sessionsData.sessions || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const stats = {
    totalDisputes: disputes.length,
    bothPartiesJoined: disputes.filter(d => d.has_tenant && d.has_landlord).length,
    waitingForParty: disputes.filter(d => !d.has_tenant || !d.has_landlord).length,
    readyForPrediction: disputes.filter(d => d.status === 'both_complete' || d.status === 'ready_for_mediation').length,
    totalSessions: sessions.length,
    completeSessions: sessions.filter(s => s.is_complete).length,
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
              <Home className="h-4 w-4" />
            </Link>
            <h1 className="text-xl font-semibold">Admin Dashboard</h1>
          </div>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 space-y-8">
        {error && (
          <Card className="border-destructive">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 text-destructive">
                <AlertCircle className="h-4 w-4" />
                <span>{error}</span>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Disputes</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalDisputes}</div>
              <p className="text-xs text-muted-foreground">
                {stats.waitingForParty} waiting for party
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Both Parties Joined</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.bothPartiesJoined}</div>
              <p className="text-xs text-muted-foreground">
                Ready for mediation
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Ready for Prediction</CardTitle>
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.readyForPrediction}</div>
              <p className="text-xs text-muted-foreground">
                Intake complete
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalSessions}</div>
              <p className="text-xs text-muted-foreground">
                {stats.completeSessions} completed
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Disputes</CardTitle>
            <CardDescription>
              All dispute cases with linked tenant and landlord sessions
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[400px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Dispute ID</TableHead>
                    <TableHead>Invite Code</TableHead>
                    <TableHead>Property</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Parties</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {disputes.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                        No disputes found
                      </TableCell>
                    </TableRow>
                  ) : (
                    disputes.map((dispute) => (
                      <TableRow key={dispute.dispute_id}>
                        <TableCell className="font-mono text-sm">
                          {dispute.dispute_id}
                        </TableCell>
                        <TableCell>
                          <code className="px-2 py-1 bg-muted rounded text-sm">
                            {dispute.invite_code}
                          </code>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate">
                          {dispute.property_address || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getStatusBadgeVariant(dispute.status)}>
                            {formatStatus(dispute.status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Badge variant={dispute.has_tenant ? 'default' : 'outline'}>
                              T
                            </Badge>
                            <Badge variant={dispute.has_landlord ? 'default' : 'outline'}>
                              L
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(dispute.created_at)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm">
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sessions</CardTitle>
            <CardDescription>
              All intake sessions (may or may not be linked to disputes)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[300px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Session ID</TableHead>
                    <TableHead>Case ID</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sessions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                        No sessions found
                      </TableCell>
                    </TableRow>
                  ) : (
                    sessions.map((session) => (
                      <TableRow key={session.session_id}>
                        <TableCell className="font-mono text-sm">
                          {session.session_id}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {session.case_id}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {formatStatus(session.stage)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {session.is_complete ? (
                            <Badge variant="default">Complete</Badge>
                          ) : (
                            <Badge variant="secondary">In Progress</Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
