import Link from 'next/link';
import { AlertTriangle, Scale, Github, ExternalLink } from 'lucide-react';
import { ROUTES } from '@/lib/constants/routes';

export function Footer() {
  return (
    <footer className="border-t bg-muted/30">
      {/* Legal Disclaimer */}
      <div className="container py-4 border-b">
        <div className="flex items-start gap-3 p-4 rounded-lg bg-warning/5 border border-warning/20">
          <div className="p-1.5 rounded-lg bg-warning/10 text-warning shrink-0">
            <AlertTriangle className="h-4 w-4" />
          </div>
          <div className="text-sm text-muted-foreground leading-relaxed">
            <strong className="text-foreground">Important Disclaimer:</strong>{' '}
            This service provides legal information based on analysis of tribunal decisions, 
            not legal advice. Results are predictions and may not reflect the outcome of your 
            specific case. Always consult a qualified legal professional for advice specific 
            to your situation.
          </div>
        </div>
      </div>
      
      {/* Footer content */}
      <div className="container py-8">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Logo and tagline */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Scale className="h-5 w-5" />
            </div>
            <div>
              <span className="font-semibold">Proposer</span>
              <p className="text-xs text-muted-foreground">
                AI-Powered Deposit Dispute Resolution
              </p>
            </div>
          </div>
          
          {/* Links */}
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link 
              href={ROUTES.HOME} 
              className="hover:text-foreground transition-colors"
            >
              Home
            </Link>
            <Link 
              href="#how-it-works" 
              className="hover:text-foreground transition-colors"
            >
              How it works
            </Link>
            <a 
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 hover:text-foreground transition-colors"
            >
              <Github className="h-4 w-4" />
              <span className="hidden sm:inline">GitHub</span>
            </a>
          </div>
          
          {/* Copyright */}
          <div className="text-sm text-muted-foreground">
            <p>© {new Date().getFullYear()} Proposer. Built for university project.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
