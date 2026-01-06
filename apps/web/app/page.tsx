import Link from 'next/link';
import { Header } from '@/components/shared/Header';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';
import {
  Scale,
  MessageSquare,
  Search,
  Brain,
  FileCheck,
  ArrowRight,
  Shield,
  Users,
  Sparkles,
  BookOpen,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';

const features = [
  {
    icon: MessageSquare,
    title: 'Guided Intake',
    description: 'Answer simple questions about your dispute through our chat interface.',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-500/10',
  },
  {
    icon: Search,
    title: 'Case Analysis',
    description: 'We analyze 500+ tribunal decisions to find similar cases.',
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-500/10',
  },
  {
    icon: Brain,
    title: 'AI Prediction',
    description: 'Get outcome predictions based on how similar cases were decided.',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-500/10',
  },
  {
    icon: FileCheck,
    title: 'Cited Sources',
    description: 'Every prediction includes citations to actual tribunal decisions.',
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-500/10',
  },
];

const stats = [
  { value: '500+', label: 'Tribunal Decisions', icon: BookOpen },
  { value: '75%', label: 'Average Accuracy', icon: TrendingUp },
  { value: '10 min', label: 'Time to Prediction', icon: Sparkles },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero Section - Compact */}
        <section className="relative py-16 px-4 overflow-hidden">
          {/* Background */}
          <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
          <div className="absolute top-20 left-1/4 w-64 h-64 bg-primary/5 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-accent/5 rounded-full blur-3xl" />
          
          <div className="relative max-w-4xl mx-auto text-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary mb-6">
              <Shield className="h-3.5 w-3.5" />
              <span>AI-Powered Legal Information</span>
              <span className="h-1 w-1 rounded-full bg-primary/50" />
              <span className="text-muted-foreground">Beta</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
              Resolve Your Deposit Dispute{' '}
              <span className="text-primary">Fairly</span>
            </h1>

            {/* Subheadline */}
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-6">
              Get a prediction of how a tribunal would likely decide your tenancy
              deposit dispute, based on <span className="font-medium text-foreground">500+ real tribunal decisions</span>.
            </p>

            {/* CTA */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
              <Button asChild size="lg" className="gap-2 h-11 px-6">
                <Link href={ROUTES.CHAT}>
                  Start Your Case
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" asChild className="h-11 px-6">
                <Link href="#how-it-works">Learn More</Link>
              </Button>
            </div>

            {/* Trust badges */}
            <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              {['Based on real tribunal decisions', 'Clear citations', 'Free during beta'].map((item) => (
                <div key={item} className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Stats - Compact */}
        <section className="py-8 border-y bg-muted/30">
          <div className="max-w-4xl mx-auto px-4">
            <div className="grid grid-cols-3 gap-6">
              {stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div key={stat.label} className="text-center">
                    <div className="inline-flex items-center justify-center p-2 rounded-xl bg-primary/10 text-primary mb-2">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="text-2xl sm:text-3xl font-bold text-primary tabular-nums">
                      {stat.value}
                    </div>
                    <div className="text-xs text-muted-foreground">{stat.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* How it Works - Compact */}
        <section id="how-it-works" className="py-12 px-4">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">How It Works</h2>
              <p className="text-muted-foreground">
                Four simple steps to understand your case
              </p>
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {features.map((feature, index) => {
                const Icon = feature.icon;
                return (
                  <div 
                    key={feature.title} 
                    className="p-4 rounded-xl border bg-card hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-center gap-3 mb-2">
                      <div className={`p-2 rounded-lg ${feature.bg}`}>
                        <Icon className={`h-4 w-4 ${feature.color}`} />
                      </div>
                      <span className="text-xs font-medium text-muted-foreground">Step {index + 1}</span>
                    </div>
                    <h3 className="font-semibold mb-1">{feature.title}</h3>
                    <p className="text-sm text-muted-foreground">{feature.description}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* For Who - Compact */}
        <section className="py-12 px-4 bg-muted/30">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Who Is This For?</h2>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              {/* Tenant */}
              <div className="p-5 rounded-xl border bg-card">
                <div className="flex items-center gap-3 mb-3">
                  <div className="p-2 rounded-lg bg-blue-500/10">
                    <Users className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <h3 className="font-semibold text-lg">Tenants</h3>
                </div>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {['Disputing unfair deposit deductions', 'Want to know chances before ADR', 'Need evidence from similar cases'].map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Landlord */}
              <div className="p-5 rounded-xl border bg-card">
                <div className="flex items-center gap-3 mb-3">
                  <div className="p-2 rounded-lg bg-amber-500/10">
                    <Scale className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <h3 className="font-semibold text-lg">Landlords</h3>
                </div>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {['Want realistic claim assessment', 'Looking for fair settlement amounts', 'Need to understand precedents'].map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* CTA - Compact */}
        <section className="py-12 px-4">
          <div className="max-w-2xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium mb-4">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              <span>Free during beta</span>
            </div>
            
            <h2 className="text-2xl font-bold mb-2">Ready to Get Started?</h2>
            <p className="text-muted-foreground mb-6">
              Answer a few questions and get a prediction in ~10 minutes.
            </p>
            
            <Button asChild size="lg" className="gap-2 h-11 px-8">
              <Link href={ROUTES.CHAT}>
                Start Your Case
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            
            <p className="mt-4 text-xs text-muted-foreground">
              No signup needed • 100% private
            </p>
          </div>
        </section>

        {/* Footer Disclaimer */}
        <footer className="border-t py-6 px-4 bg-muted/30">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-warning/5 border border-warning/20 mb-6">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground">
                <strong className="text-foreground">Important:</strong> This service provides legal information, not legal advice. 
                Results are predictions based on similar cases and may not reflect your specific outcome. 
                Consult a qualified legal professional for advice.
              </p>
            </div>
            
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <Scale className="h-4 w-4 text-primary" />
                <span className="font-medium">Proposer</span>
                <span>• AI-Powered Deposit Dispute Resolution</span>
              </div>
              <p>© {new Date().getFullYear()} Built for university project</p>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}
