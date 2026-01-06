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
  Sparkles,
  BookOpen,
  TrendingUp,
  CheckCircle2,
} from 'lucide-react';

const features = [
  {
    icon: MessageSquare,
    title: 'Guided Intake',
    description:
      'Answer simple questions about your dispute through our conversational interface.',
    color: 'from-blue-500/20 to-indigo-500/20',
    iconColor: 'text-blue-600 dark:text-blue-400',
  },
  {
    icon: Search,
    title: 'Case Analysis',
    description:
      'We analyze 500+ real tribunal decisions to find cases similar to yours.',
    color: 'from-emerald-500/20 to-teal-500/20',
    iconColor: 'text-emerald-600 dark:text-emerald-400',
  },
  {
    icon: Brain,
    title: 'AI Prediction',
    description:
      'Get a prediction of likely outcomes based on how similar cases were decided.',
    color: 'from-amber-500/20 to-orange-500/20',
    iconColor: 'text-amber-600 dark:text-amber-400',
  },
  {
    icon: FileCheck,
    title: 'Transparent Reasoning',
    description:
      'Every prediction comes with citations to actual tribunal decisions you can verify.',
    color: 'from-purple-500/20 to-pink-500/20',
    iconColor: 'text-purple-600 dark:text-purple-400',
  },
];

const stats = [
  { value: '500+', label: 'Tribunal Decisions', icon: BookOpen },
  { value: '75%', label: 'Average Accuracy', icon: TrendingUp },
  { value: '10 min', label: 'Time to Prediction', icon: Sparkles },
];

const benefits = [
  'Based on real tribunal decisions',
  'Clear citations for every claim',
  'Free to use during beta',
  'No legal jargon',
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero Section */}
        <section className="relative overflow-hidden">
          {/* Background decoration */}
          <div className="absolute inset-0 bg-gradient-hero" />
          <div className="absolute inset-0 pattern-dots opacity-30" style={{ backgroundSize: '32px 32px' }} />
          <div className="absolute top-20 left-1/4 w-72 h-72 bg-primary/5 rounded-full blur-3xl" />
          <div className="absolute bottom-10 right-1/4 w-96 h-96 bg-accent/5 rounded-full blur-3xl" />
          
          <div className="relative py-24 px-4 sm:py-32">
            <div className="container max-w-5xl mx-auto">
              <div className="flex flex-col items-center text-center stagger-children">
                {/* Badge */}
                <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-2 text-sm font-medium text-primary backdrop-blur-sm">
                  <Shield className="h-4 w-4" />
                  <span>AI-Powered Legal Information</span>
                  <span className="h-1 w-1 rounded-full bg-primary/50" />
                  <span className="text-muted-foreground">Beta</span>
                </div>

                {/* Main headline */}
                <h1 className="mt-8 text-4xl sm:text-5xl md:text-6xl font-bold tracking-tightest max-w-3xl">
                  Resolve Your Deposit Dispute{' '}
                  <span className="relative">
                    <span className="text-gradient-accent">Fairly</span>
                    <svg className="absolute -bottom-2 left-0 w-full" viewBox="0 0 200 8" fill="none">
                      <path d="M1 5.5C47 2 153 2 199 5.5" stroke="hsl(var(--accent))" strokeWidth="3" strokeLinecap="round" opacity="0.4"/>
                    </svg>
                  </span>
                </h1>

                {/* Subheadline */}
                <p className="mt-6 text-lg sm:text-xl text-muted-foreground max-w-2xl leading-relaxed">
                  Get a prediction of how a tribunal would likely decide your tenancy
                  deposit dispute, based on analysis of{' '}
                  <span className="font-semibold text-foreground">500+ real tribunal decisions</span>.
                </p>

                {/* Benefits list */}
                <div className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2">
                  {benefits.map((benefit) => (
                    <div key={benefit} className="flex items-center gap-2 text-sm text-muted-foreground">
                      <CheckCircle2 className="h-4 w-4 text-success" />
                      <span>{benefit}</span>
                    </div>
                  ))}
                </div>

                {/* CTA buttons */}
                <div className="mt-10 flex flex-col sm:flex-row gap-4">
                  <Button asChild size="lg" className="gap-2 h-12 px-8 text-base shadow-soft hover:shadow-lg transition-all duration-300 hover:-translate-y-0.5">
                    <Link href={ROUTES.CHAT}>
                      Start Your Case
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button variant="outline" size="lg" asChild className="h-12 px-8 text-base backdrop-blur-sm bg-background/50">
                    <Link href="#how-it-works">Learn How It Works</Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="relative py-16 border-y bg-muted/30">
          <div className="absolute inset-0 pattern-grid opacity-50" style={{ backgroundSize: '40px 40px' }} />
          <div className="relative container max-w-5xl mx-auto px-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
              {stats.map((stat, index) => {
                const Icon = stat.icon;
                return (
                  <div 
                    key={stat.label} 
                    className="flex flex-col items-center text-center group animate-fade-in-up"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="mb-4 p-3 rounded-2xl bg-primary/10 text-primary transition-transform duration-300 group-hover:scale-110">
                      <Icon className="h-6 w-6" />
                    </div>
                    <div className="text-4xl md:text-5xl font-bold tracking-tighter text-primary tabular-nums">
                      {stat.value}
                    </div>
                    <div className="mt-1 text-sm font-medium text-muted-foreground">
                      {stat.label}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section id="how-it-works" className="py-24 px-4 relative">
          <div className="absolute top-0 right-0 w-1/2 h-1/2 bg-gradient-to-bl from-primary/5 to-transparent rounded-full blur-3xl" />
          
          <div className="container max-w-5xl mx-auto relative">
            <div className="text-center mb-16">
              <span className="inline-block px-3 py-1 text-sm font-medium text-primary bg-primary/10 rounded-full mb-4">
                Simple Process
              </span>
              <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
                How It Works
              </h2>
              <p className="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
                Our system uses AI to analyze your case and predict outcomes based
                on real tribunal decisions.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              {features.map((feature, index) => {
                const Icon = feature.icon;
                return (
                  <Card 
                    key={feature.title} 
                    className="group relative overflow-hidden border-0 shadow-soft hover:shadow-lg transition-all duration-300 hover:-translate-y-1 bg-card"
                  >
                    {/* Gradient background */}
                    <div className={`absolute inset-0 bg-gradient-to-br ${feature.color} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />
                    
                    <CardHeader className="relative pb-2">
                      <div className="flex items-start gap-4">
                        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-background shadow-soft border ${feature.iconColor}`}>
                          <Icon className="h-6 w-6" />
                        </div>
                        <div className="space-y-1">
                          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-xs font-bold text-primary">
                            {index + 1}
                          </span>
                          <CardTitle className="text-xl">{feature.title}</CardTitle>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="relative">
                      <CardDescription className="text-base leading-relaxed">
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
        <section className="py-24 px-4 bg-muted/30 relative overflow-hidden">
          <div className="absolute inset-0 pattern-dots opacity-20" style={{ backgroundSize: '24px 24px' }} />
          <div className="absolute bottom-0 left-0 w-1/3 h-1/2 bg-gradient-to-tr from-accent/5 to-transparent rounded-full blur-3xl" />
          
          <div className="container max-w-5xl mx-auto relative">
            <div className="text-center mb-16">
              <span className="inline-block px-3 py-1 text-sm font-medium text-primary bg-primary/10 rounded-full mb-4">
                Built For You
              </span>
              <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">
                Who Is This For?
              </h2>
            </div>

            <div className="grid md:grid-cols-2 gap-8">
              {/* Tenant Card */}
              <Card className="group relative overflow-hidden border-0 shadow-soft hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-indigo-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <CardHeader className="relative">
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-2xl bg-blue-500/10">
                      <Users className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                    </div>
                    <CardTitle className="text-2xl">Tenants</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="relative">
                  <ul className="space-y-3">
                    {[
                      'Disputing unfair deductions from your deposit',
                      'Want to know your chances before ADR or tribunal',
                      'Need evidence of what similar cases decided',
                    ].map((item, i) => (
                      <li key={i} className="flex items-start gap-3 text-muted-foreground">
                        <CheckCircle2 className="h-5 w-5 text-success shrink-0 mt-0.5" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>

              {/* Landlord Card */}
              <Card className="group relative overflow-hidden border-0 shadow-soft hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
                <div className="absolute inset-0 bg-gradient-to-br from-amber-500/10 to-orange-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                <CardHeader className="relative">
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-2xl bg-amber-500/10">
                      <Scale className="h-8 w-8 text-amber-600 dark:text-amber-400" />
                    </div>
                    <CardTitle className="text-2xl">Landlords</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="relative">
                  <ul className="space-y-3">
                    {[
                      'Want a realistic assessment of your claim',
                      'Looking for fair settlement amounts',
                      'Need to understand tribunal precedents',
                    ].map((item, i) => (
                      <li key={i} className="flex items-start gap-3 text-muted-foreground">
                        <CheckCircle2 className="h-5 w-5 text-success shrink-0 mt-0.5" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-24 px-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background via-primary/5 to-background" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/10 rounded-full blur-3xl" />
          
          <div className="container max-w-3xl mx-auto text-center relative">
            <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-4 py-2 text-sm font-medium text-accent-foreground mb-6">
              <Sparkles className="h-4 w-4 text-accent" />
              <span>Free during beta</span>
            </div>
            
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">
              Ready to Get Started?
            </h2>
            <p className="text-lg text-muted-foreground mb-10 max-w-xl mx-auto">
              Answer a few questions about your dispute and get a prediction in
              about 10 minutes. No signup required.
            </p>
            
            <Button asChild size="lg" className="gap-2 h-14 px-10 text-lg shadow-glow hover:shadow-glow-accent transition-all duration-300 hover:-translate-y-1">
              <Link href={ROUTES.CHAT}>
                Start Your Case
                <ArrowRight className="h-5 w-5" />
              </Link>
            </Button>
            
            <p className="mt-6 text-sm text-muted-foreground">
              Takes ~10 minutes • No signup needed • 100% private
            </p>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
