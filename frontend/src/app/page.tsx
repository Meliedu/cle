import Link from "next/link";
import {
  BrainCircuit,
  Languages,
  Mic,
  Sparkles,
  GraduationCap,
  ArrowRight,
} from "lucide-react";

const features = [
  {
    icon: BrainCircuit,
    title: "Smart Quizzes",
    description:
      "AI-generated quizzes that adapt to your learning pace and focus on areas you need most.",
  },
  {
    icon: Sparkles,
    title: "AI Flashcards",
    description:
      "Automatically generated flashcards from your course materials with spaced repetition.",
  },
  {
    icon: Mic,
    title: "Pronunciation Practice",
    description:
      "Real-time feedback on your pronunciation with tone and accent analysis.",
  },
  {
    icon: Languages,
    title: "Multilingual Support",
    description:
      "Learn Chinese, English, Japanese, or Korean with materials tailored to your level.",
  },
] as const;

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--color-bg)]">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 md:px-12">
        <div className="flex items-center gap-2">
          <GraduationCap className="size-7 text-[var(--color-primary)]" />
          <span className="text-xl font-bold tracking-tight text-[var(--color-text)]">
            Meli
          </span>
        </div>
        <nav className="flex items-center gap-3">
          <Link
            href="/sign-in"
            className="rounded-[var(--radius-lg)] px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text)]"
          >
            Sign In
          </Link>
          <Link
            href="/sign-up"
            className="rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-primary-hover)] hover:shadow-[var(--shadow-md)]"
          >
            Get Started
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <main className="flex flex-1 flex-col">
        <section className="relative flex flex-col items-center px-6 pb-16 pt-16 text-center md:px-12 md:pt-24 lg:pt-32">
          {/* Decorative gradient blob */}
          <div
            className="pointer-events-none absolute top-0 left-1/2 -z-10 -translate-x-1/2 opacity-30"
            aria-hidden="true"
          >
            <div
              className="h-[400px] w-[600px] rounded-full"
              style={{
                background:
                  "radial-gradient(ellipse at center, var(--color-primary-light) 0%, transparent 70%)",
              }}
            />
          </div>

          <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)]">
            <GraduationCap className="size-3.5" />
            Built for HKUST
          </div>

          <h1 className="mt-6 max-w-3xl text-[var(--text-4xl)] font-bold leading-[1.1] tracking-tight text-[var(--color-text)]">
            Learn languages smarter{" "}
            <span className="text-[var(--color-primary)]">with AI</span>
          </h1>

          <p className="mt-4 max-w-xl text-[var(--text-lg)] leading-relaxed text-[var(--color-text-secondary)]">
            An intelligent language learning assistant designed for HKUST
            instructors and students. Upload materials, generate quizzes, and
            practice with AI-powered feedback.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link
              href="/sign-up"
              className="group inline-flex items-center gap-2 rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-6 py-3 text-sm font-medium text-white transition-all duration-[var(--duration-normal)] ease-[var(--ease-out)] hover:bg-[var(--color-primary-hover)] hover:shadow-[var(--shadow-lg)]"
            >
              Start Learning
              <ArrowRight className="size-4 transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/sign-in"
              className="inline-flex items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-3 text-sm font-medium text-[var(--color-text)] transition-all duration-[var(--duration-normal)] ease-[var(--ease-out)] hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)] hover:shadow-[var(--shadow-sm)]"
            >
              Sign In
            </Link>
          </div>
        </section>

        {/* Features */}
        <section className="px-6 pb-24 md:px-12">
          <div className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="group rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition-all duration-[var(--duration-normal)] ease-[var(--ease-out)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]"
              >
                <div className="mb-3 inline-flex rounded-[var(--radius-md)] bg-[var(--color-primary-light)] p-2 text-[var(--color-primary)] transition-colors duration-[var(--duration-fast)] group-hover:bg-[var(--color-primary)] group-hover:text-white">
                  <feature.icon className="size-5" />
                </div>
                <h3 className="text-sm font-semibold text-[var(--color-text)]">
                  {feature.title}
                </h3>
                <p className="mt-1 text-[var(--text-sm)] leading-relaxed text-[var(--color-text-muted)]">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--color-border)] px-6 py-6 text-center text-[var(--text-sm)] text-[var(--color-text-muted)] md:px-12">
        HKUST Center for Language Education
      </footer>
    </div>
  );
}
