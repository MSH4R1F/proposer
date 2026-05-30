import Link from 'next/link';
import { Header } from '@/components/shared/Header';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { ROUTES } from '@/lib/constants/routes';
import {
  Scale,
  MessageSquare,
  Search,
  Network,
  FileCheck,
  ArrowRight,
  Shield,
  ShieldCheck,
  Users,
  Sparkles,
  BookOpen,
  Layers,
  Calendar,
  Eye,
  CheckCircle2,
  AlertTriangle,
  Check,
  X,
} from 'lucide-react';

const features = [
  {
    icon: MessageSquare,
    title: 'Tell us what happened',
    description:
      'A guided intake walks you through the dispute, your evidence, and the timeline — no legal jargon required.',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-500/10',
  },
  {
    icon: Network,
    title: 'We map your dispute',
    description:
      'Proposer builds a knowledge graph of your facts, evidence, and dates so nothing important gets lost.',
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-500/10',
  },
  {
    icon: Search,
    title: 'We find similar real cases',
    description:
      'The system retrieves comparable past tribunal decisions and predicts the likely outcome of yours.',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-500/10',
  },
  {
    icon: FileCheck,
    title: 'Cited reasoning + fair offer',
    description:
      'See the transparent reasoning trace behind every conclusion, then negotiate within a realistic settlement range.',
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-500/10',
  },
];

const stats = [
  { value: '4,336', label: 'Real UK tribunal cases indexed', icon: BookOpen },
  { value: '43,776', label: 'Searchable passages behind every prediction', icon: Layers },
  { value: '2020–2023', label: 'Years covered, plus 1,000 Housing Ombudsman rulings', icon: Calendar },
];

const comparison = [
  {
    feature: 'Grounded in real decisions',
    proposer: 'Every claim cited to a real tribunal case',
    chatbot: 'Trained on the open web — rarely cited',
    diy: 'Yes, but you do the digging',
  },
  {
    feature: 'Tells you when it’s unsure',
    proposer: 'Cite-or-abstain — says “uncertain”',
    chatbot: 'Confidently guesses',
    diy: 'N/A',
  },
  {
    feature: 'Predicts the likely outcome',
    proposer: 'From 4,336 similar real cases',
    chatbot: 'No, or unverifiable',
    diy: 'Only after you file',
  },
  {
    feature: 'Helps you settle',
    proposer: 'Shadow mediator finds a fair range',
    chatbot: 'No',
    diy: 'Slow and adversarial',
  },
];

const honesty = [
  {
    icon: ShieldCheck,
    title: 'Cite-or-abstain',
    description:
      'If Proposer can’t back a claim with a real tribunal decision, it tells you it’s uncertain — it won’t invent something to sound confident.',
  },
  {
    icon: Eye,
    title: 'Glass-box reasoning',
    description:
      'No black box. Every prediction comes with its reasoning trace and the exact cases behind it, so you can check our work.',
  },
  {
    icon: Scale,
    title: 'Information, not advice',
    description:
      'Proposer gives you clear, evidence-based legal information to make your own decisions — it never pretends to be your solicitor.',
  },
];

const faqs = [
  {
    q: 'Is this legal advice?',
    a: 'No. Proposer provides legal information grounded in real tribunal decisions to help you understand your position. For formal advice on your specific situation, speak to a qualified solicitor.',
  },
  {
    q: 'How do I know it isn’t just making things up?',
    a: 'Because of our cite-or-abstain rule: every factual claim is linked to a specific real tribunal decision, and when the evidence isn’t there, Proposer says “uncertain” rather than guessing.',
  },
  {
    q: 'Can it guarantee I’ll win or get my deposit back?',
    a: 'No, and we’d be suspicious of anything that did. Proposer shows the likely outcome based on how similar past disputes were decided — outcomes always depend on your specific facts and evidence.',
  },
  {
    q: 'What does it cost?',
    a: 'Proposer is free while in beta. You can start a case without signing up for anything paid.',
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero Section */}
        <section className="relative py-16 px-4 overflow-hidden">
          {/* Background */}
          <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
          <div className="absolute top-20 left-1/4 w-64 h-64 bg-primary/5 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-accent/5 rounded-full blur-3xl" />

          <div className="relative max-w-4xl mx-auto text-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary mb-6">
              <Shield className="h-3.5 w-3.5" />
              <span>Now in open beta</span>
              <span className="h-1 w-1 rounded-full bg-primary/50" />
              <span className="text-muted-foreground">Free while in beta</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
              Every prediction, cited to a{' '}
              <span className="text-primary">real tribunal decision</span>.
            </h1>

            {/* Subheadline */}
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-6">
              Proposer reads your dispute, finds similar real cases from UK tribunals, and shows the
              likely outcome — every claim cited to an actual decision. Then it helps both sides
              reach a fair settlement, without court.
            </p>

            {/* CTA */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
              <Button asChild size="lg" className="gap-2 h-11 px-6">
                <Link href={ROUTES.CHAT}>
                  Start my case — free
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" asChild className="h-11 px-6">
                <Link href="#how-it-works">See how it works</Link>
              </Button>
            </div>

            {/* Trust badges */}
            <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              {[
                'Built on 4,336 real tribunal cases',
                'Every claim cited — or it says “uncertain”',
                'Legal information, not legal advice',
              ].map((item) => (
                <div key={item} className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Stats */}
        <section className="py-8 border-y bg-muted/30">
          <div className="max-w-4xl mx-auto px-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
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

        {/* How it Works */}
        <section id="how-it-works" className="py-12 px-4">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">How It Works</h2>
              <p className="text-muted-foreground">
                From your story to cited reasoning, in four steps
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
                      <span className="text-xs font-medium text-muted-foreground">
                        Step {index + 1}
                      </span>
                    </div>
                    <h3 className="font-semibold mb-1">{feature.title}</h3>
                    <p className="text-sm text-muted-foreground">{feature.description}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Why Proposer is different */}
        <section className="py-12 px-4 bg-muted/30">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Why Proposer Is Different</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Most “legal AI” guesses confidently and cites nothing. Traditional routes are slow
                and expensive. Proposer sits in between — fast, grounded, and honest about what it
                doesn’t know.
              </p>
            </div>

            <div className="rounded-xl border bg-card overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-[28%]"></TableHead>
                    <TableHead className="text-primary font-semibold">Proposer</TableHead>
                    <TableHead>Generic legal chatbots</TableHead>
                    <TableHead>Court · DIY</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {comparison.map((row) => (
                    <TableRow key={row.feature} className="hover:bg-transparent">
                      <TableCell className="font-medium text-foreground align-top">
                        {row.feature}
                      </TableCell>
                      <TableCell className="bg-primary/5 align-top">
                        <span className="flex items-start gap-2">
                          <Check className="h-4 w-4 text-success shrink-0 mt-0.5" />
                          <span className="text-foreground">{row.proposer}</span>
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground align-top">
                        <span className="flex items-start gap-2">
                          <X className="h-4 w-4 text-muted-foreground/60 shrink-0 mt-0.5" />
                          <span>{row.chatbot}</span>
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground align-top">{row.diy}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </section>

        {/* For Who */}
        <section className="py-12 px-4">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Who Is This For?</h2>
              <p className="text-muted-foreground">
                The same precedent, applied fairly to both sides
              </p>
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
                  {[
                    'See whether your landlord’s deductions hold up against how real tribunals have ruled',
                    'Walk into negotiation knowing the realistic range — and what a fair offer looks like',
                    'Free during beta, private, and no lawyer required to get started',
                  ].map((item) => (
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
                  {[
                    'Check your position before a dispute escalates and guard against unrealistic counter-claims',
                    'Anchor negotiation in cited precedent instead of back-and-forth emails',
                    'Resolve faster and cheaper than a tribunal hearing, with a clear paper trail',
                  ].map((item) => (
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

        {/* How we keep it honest */}
        <section className="py-12 px-4 bg-muted/30">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">How We Keep It Honest</h2>
              <p className="text-muted-foreground">
                Transparency is the product, not a footnote
              </p>
            </div>

            <div className="grid sm:grid-cols-3 gap-4">
              {honesty.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="p-5 rounded-xl border bg-card">
                    <div className="inline-flex items-center justify-center p-2 rounded-lg bg-primary/10 text-primary mb-3">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="font-semibold mb-1">{item.title}</h3>
                    <p className="text-sm text-muted-foreground">{item.description}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="py-12 px-4">
          <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold mb-2">Frequently Asked Questions</h2>
            </div>

            <Accordion type="single" collapsible className="rounded-xl border bg-card px-4">
              {faqs.map((faq) => (
                <AccordionItem key={faq.q} value={faq.q} className="last:border-b-0">
                  <AccordionTrigger className="text-left text-sm">{faq.q}</AccordionTrigger>
                  <AccordionContent className="text-sm text-muted-foreground">
                    {faq.a}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </section>

        {/* CTA */}
        <section className="py-12 px-4 bg-muted/30">
          <div className="max-w-2xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium mb-4">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              <span>Free during beta</span>
            </div>

            <h2 className="text-2xl font-bold mb-2">
              Find out where you stand — in minutes, not months.
            </h2>
            <p className="text-muted-foreground mb-6">
              Start your case and see the likely outcome, cited to real tribunal decisions, before
              you negotiate or file.
            </p>

            <Button asChild size="lg" className="gap-2 h-11 px-8">
              <Link href={ROUTES.CHAT}>
                Start my case — free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>

            <p className="mt-4 text-xs text-muted-foreground">
              No paywall • Private to you • Free during beta
            </p>
          </div>
        </section>

        {/* Footer Disclaimer */}
        <footer className="border-t py-6 px-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-start gap-3 p-4 rounded-lg bg-warning/5 border border-warning/20 mb-6">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground">
                <strong className="text-foreground">Important:</strong> Proposer provides legal
                information, not legal advice, and does not create a solicitor–client relationship.
                Predictions are based on patterns in past UK First-tier Tribunal (Property Chamber)
                and Housing Ombudsman decisions and do not guarantee any outcome in your case. Always
                consult a qualified legal professional before making decisions about your dispute.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <Scale className="h-4 w-4 text-primary" />
                <span className="font-medium">Proposer</span>
                <span>• AI-Powered Tribunal Outcome Prediction</span>
              </div>
              <p>© {new Date().getFullYear()} Built for university project</p>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}
