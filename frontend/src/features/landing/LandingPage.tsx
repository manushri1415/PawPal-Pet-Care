import './LandingPage.css';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { BrandBadge } from '../../components/BrandBadge';
import { PeekingPet } from '../../components/PeekingPet';
import { PetOverlayLoop } from '../../components/PetOverlayLoop';
import { SidePeekingPet } from '../../components/SidePeekingPet';
import { BellIcon, CheckIcon, ClockIcon, FileTextIcon, PawIcon } from '../../components/icons';
import { overlayLoops, peekingCats, sidePeekingCat } from '../../assets/pets';

const REPO_URL = 'https://github.com/manushri1415/PawPal-Pet-Care';
const AUTHOR_URL = 'https://www.manushri.dev/';

/**
 * The public front of the app — a small pet shop rather than a dashboard.
 * Everything a visitor needs to know before they walk in: what PawPal+ does,
 * why it exists, and the one thing it never does (invent a date or a dose).
 * The only way in is the "Open PawPal" button, which goes to /app.
 *
 * Reuses the app's tokens, buttons and the pet illustrations, but with its
 * own layout language (a storytelling scroll with scene-sized art) so it does
 * not read as one more card grid. Character budget follows the art house
 * rules: at most two per viewport, each with a reason to be where it is —
 * and the artwork stops at what is here (dog, two cats, paw prints).
 */
export function LandingPage() {
  useEffect(() => {
    const previous = document.title;
    document.title = 'PawPal+ — pet care, kept tidy';
    return () => {
      document.title = previous;
    };
  }, []);

  return (
    <div className="pp-shop">
      <div className="pp-shop__awning" aria-hidden="true" />

      <div className="pp-shop__inner">
        <header className="pp-shop-top">
          <BrandBadge />
          <nav className="pp-shop-top__actions" aria-label="Landing">
            <a className="pp-shop-top__link" href={REPO_URL} target="_blank" rel="noreferrer">
              Source
            </a>
            <OpenAppLink>Open PawPal</OpenAppLink>
          </nav>
        </header>

        <main className="pp-shop-main">
          <section className="pp-shop-hero" aria-labelledby="pp-shop-hero-title">
            <div className="pp-shop-hero__copy">
              <p className="pp-shop-eyebrow">Pet care, kept tidy</p>
              <h1 id="pp-shop-hero-title" className="pp-shop-hero__title">
                Every walk, every dose, every vet note <em className="pp-shop-hero__accent">remembered.</em>
              </h1>
              <p className="pp-shop-hero__lede">
                PawPal+ is a gentle daily planner for your pets. It sorts today's care by what matters, reads the
                vet paperwork you hand it, and only adds a reminder once you've said yes.
              </p>
              <div className="pp-shop-hero__actions">
                <OpenAppLink large>Open PawPal</OpenAppLink>
                <a className="pp-button pp-button--secondary pp-shop__cta" href="#shelf">
                  See what's on the shelf
                </a>
              </div>
              <ul className="pp-shop-hero__notes">
                <li>No account or API key needed</li>
                <li>Nothing is scheduled without your approval</li>
              </ul>
            </div>

            <ShopWindow />
          </section>

          {/* The one paw divider: the shop front above, the story below. */}
          <div className="pp-shop__divider" aria-hidden="true">
            <PawIcon />
          </div>

          <section className="pp-shop-note" aria-labelledby="pp-shop-note-title">
            <div className="pp-shop-note__copy">
              <p className="pp-shop-eyebrow">Why it exists</p>
              <h2 id="pp-shop-note-title">A shelf, not a feed.</h2>
              <p>
                Care instructions arrive as paperwork: a vaccine certificate, a discharge summary, a hand-written
                dosing note. The dates inside them quietly become deadlines, and they live in three different
                places.
              </p>
              <p>
                PawPal+ keeps them in one calm place and turns them into a day you can actually follow — walks
                and feeding beside the medication that came out of last month's visit.
              </p>
            </div>
            <figure className="pp-shop-pin">
              <span className="pp-shop-pin__tape" aria-hidden="true" />
              {/* Peeks out from behind the note's left edge, towards the story; sized in CSS. */}
              <SidePeekingPet {...sidePeekingCat} side="left" className="pp-shop-pin__cat" delay={7} />
              <blockquote className="pp-shop-pin__quote">
                I once missed a vaccine due date. The certificate, the email, the clinic printout — all real, all
                somewhere else. PawPal+ is the shelf I wished I'd had.
              </blockquote>
              <figcaption className="pp-shop-pin__by">— the note this project started from</figcaption>
            </figure>
          </section>

          <section className="pp-shop-shelf" id="shelf" aria-labelledby="pp-shop-shelf-title">
            <div className="pp-shop-section-head">
              <p className="pp-shop-eyebrow">What's on the shelf</p>
              <h2 id="pp-shop-shelf-title">Four things it does. One thing it never will.</h2>
            </div>

            {/* Tiles stand on the plank at their own heights, like jars on a shelf. */}
            <div className="pp-shop-shelf__row">
              <ShelfTile tone="sage" tag="Every day" icon={<ClockIcon />} title="Today, sorted">
                Walks, feeding and meds for every pet in one daily plan, ordered by priority and time. Overlaps get
                flagged before they bite.
              </ShelfTile>
              <ShelfTile tone="plum" tag="AI-assisted" icon={<FileTextIcon />} title="Reads the paperwork">
                Upload a vet PDF or DOCX, or paste the text. PawPal+ proposes structured records — vaccine,
                medication, follow-up — each pinned to the exact passage it came from.
              </ShelfTile>
              <ShelfTile
                tone="peach"
                tag="You decide"
                icon={<CheckIcon />}
                title="You approve, then it counts"
                // The shortest jar: the cat hops onto its top edge, between its taller neighbours.
                peek={<PeekingPet {...peekingCats.gray} className="pp-shop-shelf__peek" y={-1} delay={3} duration={12} />}
              >
                Nothing is saved or scheduled until you approve, edit or reject each record. The AI suggests; you
                have the last word.
              </ShelfTile>
              <ShelfTile tone="terracotta" tag="No guessing" icon={<BellIcon />} title="Reminders that do the math">
                Approved facts become due dates and reminders through plain code, never a model's estimate. When
                two documents disagree, it says so instead of smoothing it over.
              </ShelfTile>
            </div>
            <div className="pp-shop-shelf__plank" aria-hidden="true" />

            {/* The "one thing it never will": a small sign hanging under the shelf. */}
            <aside className="pp-shop-never" aria-labelledby="pp-shop-never-title">
              <p className="pp-shop-never__eyebrow">The one thing it never will</p>
              <h3 id="pp-shop-never-title" className="pp-shop-never__title">
                Never acts without you
              </h3>
              <p className="pp-shop-never__body">PawPal+ can suggest. You decide what becomes part of care.</p>
            </aside>
          </section>

          <section className="pp-shop-rules" id="how" aria-labelledby="pp-shop-rules-title">
            <div className="pp-shop-section-head">
              <p className="pp-shop-eyebrow">House rules</p>
              <h2 id="pp-shop-rules-title">How the work is split</h2>
              <p className="pp-shop-section-head__sub">
                So nothing about your pet's care is ever invented along the way.
              </p>
            </div>

            <div className="pp-shop-plaque">
              <ol className="pp-shop-plaque__rules">
                <Rule n="01" title="The AI does the reading">
                  Free-form documents in, structured fields out — and answers to your questions about them,
                  each with a citation back to the source passage.
                </Rule>
                <Rule n="02" title="Plain code does the math">
                  Dates, statuses, reminders, conflict detection and storage are deterministic Python. Same input,
                  same answer, every time.
                </Rule>
                <Rule n="03" title="A person has the last word">
                  Every extracted record waits for your approval. Nothing reaches the schedule on a model's
                  say-so.
                </Rule>
              </ol>
              <div className="pp-shop-plaque__made">
                <span className="pp-shop-plaque__made-label">Made of</span>
                <ul className="pp-shop-plaque__parts">
                  <li>FastAPI</li>
                  <li>React</li>
                  <li>SQLite</li>
                  <li>Retrieval-augmented extraction</li>
                  <li>Offline mock provider</li>
                </ul>
                <a className="pp-shop-plaque__source" href={REPO_URL} target="_blank" rel="noreferrer">
                  Read the source →
                </a>
              </div>
            </div>
          </section>

          <section className="pp-shop-close" aria-labelledby="pp-shop-close-title">
            {/* Lying on the band's top edge; a long rest, then a tail swish. Sized in CSS (it shrinks on phones). */}
            <PetOverlayLoop {...overlayLoops.restingOrangeCat} className="pp-shop-close__cat" />
            <div className="pp-shop-close__copy">
              <h2 id="pp-shop-close-title">Come on in.</h2>
              <p>Add a pet, set the routine, and let today sort itself.</p>
            </div>
            <div className="pp-shop-close__actions">
              <OpenAppLink large>Open PawPal</OpenAppLink>
              <a className="pp-shop-close__source" href={REPO_URL} target="_blank" rel="noreferrer">
                Source on GitHub
              </a>
            </div>
          </section>
        </main>

        <footer className="pp-shop-footer">
          <div className="pp-shop-footer__brand">
            <BrandBadge size="sm" />
            <span>
              Made with care by{' '}
              <a href={AUTHOR_URL} target="_blank" rel="noreferrer">
                Manushri
              </a>
            </span>
          </div>
          <p className="pp-shop-footer__note">
            PawPal+ organizes care information. It never gives medical advice — that stays with your vet.
          </p>
        </footer>
      </div>

      {/* The awning's stripes again along the bottom edge, to close the page. */}
      <div className="pp-shop__hem" aria-hidden="true" />
    </div>
  );
}

/** The one way into the app. */
function OpenAppLink({ children, large = false }: { children: ReactNode; large?: boolean }) {
  const className = ['pp-button', 'pp-button--primary', large && 'pp-shop__cta'].filter(Boolean).join(' ');
  return (
    <Link to="/app" className={className}>
      <PawIcon />
      {children}
    </Link>
  );
}

/**
 * The hero scene: the arched shop door with the dog awake on a cushion in its
 * window (the shop is open, so is the shopkeeper) — wagging its tail now and
 * then — and an "Open" sign hanging from a nail on two strings.
 */
function ShopWindow() {
  return (
    <div className="pp-shop-window" aria-hidden="true">
      <div className="pp-shop-window__frame">
        <div className="pp-shop-window__pane">
          <span className="pp-shop-sign">
            <svg className="pp-shop-sign__strings" viewBox="0 0 100 34">
              <path d="M50 3 16 34M50 3l34 31" />
              <circle cx="50" cy="3" r="2.6" />
            </svg>
            <span className="pp-shop-sign__board">
              Open
              <small>today</small>
            </span>
          </span>
          <span className="pp-shop-window__cushion" />
          <PetOverlayLoop {...overlayLoops.awakeDog} className="pp-shop-window__dog" />
        </div>
      </div>
      <div className="pp-shop-window__sill" />
    </div>
  );
}

function ShelfTile({
  tone,
  tag,
  icon,
  title,
  peek,
  children,
}: {
  tone: 'sage' | 'plum' | 'peach' | 'terracotta';
  tag: string;
  icon: ReactNode;
  title: string;
  /** Decoration on the tile's own top edge (a PeekingPet). */
  peek?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className={`pp-shop-tile pp-tone--${tone}`}>
      {peek}
      <span className="pp-shop-tile__tag">{tag}</span>
      <span className="pp-shop-tile__icon" aria-hidden="true">
        {icon}
      </span>
      <h3 className="pp-shop-tile__title">{title}</h3>
      <p className="pp-shop-tile__body">{children}</p>
    </article>
  );
}

function Rule({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <li className="pp-shop-rule">
      <span className="pp-shop-rule__n" aria-hidden="true">
        {n}
      </span>
      <h3 className="pp-shop-rule__title">{title}</h3>
      <p className="pp-shop-rule__body">{children}</p>
    </li>
  );
}
