import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Proposer - AI-Powered Deposit Dispute Resolution',
  description:
    'Get fair resolution for your tenancy deposit dispute using AI-powered legal analysis based on real tribunal decisions.',
  keywords: [
    'deposit dispute',
    'tenant rights',
    'landlord',
    'UK housing',
    'legal mediation',
    'AI legal',
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
