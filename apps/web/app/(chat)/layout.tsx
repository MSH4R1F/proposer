import { Header } from '@/components/shared/Header';
import { Footer } from '@/components/shared/Footer';

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1 container max-w-4xl py-4">
        <div className="h-[calc(100vh-10rem)] rounded-lg border bg-background shadow-sm overflow-hidden">
          {children}
        </div>
      </main>
      <Footer />
    </div>
  );
}
