import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { ROUTES } from '@/lib/constants/routes';
import { Scale, Home, ArrowRight } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="shrink-0 h-14 border-b border-border/40 flex items-center px-4">
        <Link 
          href={ROUTES.HOME} 
          className="flex items-center gap-2.5 group"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground transition-transform duration-200 group-hover:scale-105">
            <Scale className="h-4 w-4" />
          </div>
          <span className="font-semibold text-lg">Proposer</span>
        </Link>
      </header>
      
      {/* Content */}
      <main className="flex-1 flex items-center justify-center p-4">
        <div className="text-center">
          <div className="text-8xl font-bold text-muted-foreground/20 mb-4">404</div>
          <h1 className="text-2xl font-semibold mb-2">Page Not Found</h1>
          <p className="text-muted-foreground mb-8 max-w-md">
            The page you're looking for doesn't exist or has been moved.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button asChild>
              <Link href={ROUTES.HOME}>
                <Home className="h-4 w-4 mr-2" />
                Go Home
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={ROUTES.CHAT}>
                Start a Case
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </div>
        </div>
      </main>
      
      {/* Footer */}
      <footer className="shrink-0 border-t py-4 px-4 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} Proposer • AI-Powered Deposit Dispute Resolution
      </footer>
    </div>
  );
}
