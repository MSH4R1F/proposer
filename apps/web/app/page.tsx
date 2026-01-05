import Link from 'next/link';
import { Header } from '@/components/shared/Header';
import { Footer } from '@/components/shared/Footer';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ROUTES } from '@/lib/constants/routes';
import {
  Scale,
  MessageSquare,
  Search,
  FileCheck,
  ArrowRight,
  Shield,
  Brain,
  Users,
} from 'lucide-react';

const features = [
  {
    icon: MessageSquare,
    title: 'Guided Intake',
    description:
      'Answer simple questions about your dispute through our conversational interface.',
  },
  {
    icon: Search,
    title: 'Case Analysis',
    description:
      'We analyze 500+ real tribunal decisions to find cases similar to yours.',
  },
  {
    icon: Brain,
    title: 'AI Prediction',
    description:
      'Get a prediction of likely outcomes based on how similar cases were decided.',
  },
  {
    icon: FileCheck,
    title: 'Transparent Reasoning',
    description:
      'Every prediction comes with citations to actual tribunal decisions you can verify.',
  },
];

const stats = [
  { value: '500+', label: 'Tribunal Decisions' },
  { value: '75%', label: 'Average Accuracy' },
  { value: '10 min', label: 'Time to Prediction' },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero Section */}
        <section className="py-20 px-4 bg-gradient-to-b from-background to-muted/30">
          <div className="container max-w-4xl mx-auto text-center">
            <div className="inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm mb-6">
              <Shield className="h-4 w-4 text-primary" />
              <span>AI-Powered Legal Information</span>
            </div>

            <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-6">
              Resolve Your Deposit Dispute
              <span className="text-primary"> Fairly</span>
            </h1>

            <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
              Get a prediction of how a tribunal would likely decide your tenancy
              deposit dispute, based on analysis of real tribunal decisions.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button asChild size="lg" className="gap-2">
                <Link href={ROUTES.CHAT}>
                  Start Your Case
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" asChild>
                <Link href="#how-it-works">Learn More</Link>
              </Button>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="py-12 border-y bg-muted/30">
          <div className="container max-w-4xl mx-auto">
            <div className="grid grid-cols-3 gap-8 text-center">
              {stats.map((stat) => (
                <div key={stat.label}>
                  <div className="text-3xl md:text-4xl font-bold text-primary">
                    {stat.value}
                  </div>
                  <div className="text-sm text-muted-foreground">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section id="how-it-works" className="py-20 px-4">
          <div className="container max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">How It Works</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto">
                Our system uses AI to analyze your case and predict outcomes based
                on real tribunal decisions.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              {features.map((feature, index) => {
                const Icon = feature.icon;
                return (
                  <Card key={feature.title}>
                    <CardHeader>
                      <div className="flex items-center gap-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                          <Icon className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <span className="text-xs text-muted-foreground">
                            Step {index + 1}
                          </span>
                          <CardTitle className="text-lg">{feature.title}</CardTitle>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <CardDescription className="text-base">
                        {feature.description}
                      </CardDescription>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </section>

        {/* For Who Section */}
        <section className="py-20 px-4 bg-muted/30">
          <div className="container max-w-4xl mx-auto">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold mb-4">Who Is This For?</h2>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <Users className="h-6 w-6 text-primary" />
                    <CardTitle>Tenants</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-muted-foreground">
                    <li>- Disputing unfair deductions from your deposit</li>
                    <li>- Want to know your chances before ADR or tribunal</li>
                    <li>- Need evidence of what similar cases decided</li>
                  </ul>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <Scale className="h-6 w-6 text-primary" />
                    <CardTitle>Landlords</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-muted-foreground">
                    <li>- Want a realistic assessment of your claim</li>
                    <li>- Looking for fair settlement amounts</li>
                    <li>- Need to understand tribunal precedents</li>
                  </ul>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20 px-4">
          <div className="container max-w-2xl mx-auto text-center">
            <h2 className="text-3xl font-bold mb-4">Ready to Get Started?</h2>
            <p className="text-muted-foreground mb-8">
              Answer a few questions about your dispute and get a prediction in
              about 10 minutes.
            </p>
            <Button asChild size="lg" className="gap-2">
              <Link href={ROUTES.CHAT}>
                Start Your Case
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
