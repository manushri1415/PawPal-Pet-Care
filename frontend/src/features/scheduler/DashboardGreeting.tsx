import './DashboardGreeting.css';
import { useQuery } from '@tanstack/react-query';
import { getOwner, listPets, listTasks } from '../../api/scheduler';
import { PetArt } from '../../components/PetArt';
import { PetAvatar } from '../../components/PetAvatar';
import { dayOffsetFromToday } from '../../lib/datetime';
import { greetingFor, joinNames } from '../../lib/display';

/**
 * Greeting + at-a-glance overview. Read-only: it reuses the owner, pets and
 * open-tasks queries the modules below already make (same query keys, so
 * no extra requests) and only summarises them.
 */
export function DashboardGreeting() {
  const ownerQuery = useQuery({ queryKey: ['owner'], queryFn: getOwner });
  const petsQuery = useQuery({ queryKey: ['pets'], queryFn: listPets });
  // Same key TaskList uses for its default (open, all pets, default sort) view.
  const openTasksQuery = useQuery({
    queryKey: ['tasks', { petId: undefined, status: 'open', sort: undefined }],
    queryFn: () => listTasks({ petId: undefined, status: 'open', sort: undefined }),
  });

  const now = new Date();
  const pets = petsQuery.data ?? [];
  const openTasks = openTasksQuery.data ?? [];
  const dueNow = openTasks.filter((task) => (dayOffsetFromToday(task.due_date, now) ?? 0) <= 0);
  const highPriority = dueNow.filter((task) => task.priority === 'high');
  // "Pet Owner" is the placeholder name api/storage.py gives a brand-new
  // owner row; greeting someone as "Pet" reads as a bug, so skip it.
  const ownerName = ownerQuery.data?.name.trim() ?? '';
  const firstName = ownerName && ownerName.toLowerCase() !== 'pet owner' ? ownerName.split(/\s+/)[0] : undefined;
  const noPetsYet = petsQuery.isSuccess && pets.length === 0;

  let summary = 'Here’s how the day looks for your crew.';
  if (noPetsYet) {
    summary = 'Add your first companion and we’ll help you plan their care.';
  } else if (openTasksQuery.isSuccess && pets.length > 0) {
    const names = joinNames(pets.slice(0, 3).map((pet) => pet.name)) + (pets.length > 3 ? ' and friends' : '');
    summary =
      dueNow.length === 0
        ? `Everything’s handled for today. ${names} ${pets.length === 1 ? 'is' : 'are'} all set.`
        : `${dueNow.length} care ${dueNow.length === 1 ? 'task' : 'tasks'} left today for ${names}.`;
  }

  const stats = [
    { label: 'Left today', value: openTasksQuery.isSuccess ? dueNow.length : '–' },
    { label: 'High priority', value: openTasksQuery.isSuccess ? highPriority.length : '–' },
    { label: pets.length === 1 ? 'Pet' : 'Pets', value: petsQuery.isSuccess ? pets.length : '–' },
  ];

  return (
    <section className="pp-greeting" aria-labelledby="pp-greeting-title">
      <PetArt slot="greeting-motif" className="pp-greeting__motif" />

      <div className="pp-greeting__text">
        <p className="pp-greeting__date">
          {now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
        </p>
        <h1 id="pp-greeting-title" className="pp-greeting__title">
          {greetingFor(now)}
          {firstName ? `, ${firstName}` : ''}
        </h1>
        <p className="pp-greeting__summary">{summary}</p>
      </div>

      {/* A row of zeros says nothing to someone who hasn't added a pet yet. */}
      {!noPetsYet && (
        <div className="pp-greeting__side">
          {pets.length > 0 && (
            <div className="pp-greeting__avatars" aria-hidden="true">
              {pets.slice(0, 4).map((pet) => (
                <PetAvatar key={pet.pet_id} pet={pet} size="md" />
              ))}
              {pets.length > 4 && <span className="pp-greeting__more">+{pets.length - 4}</span>}
            </div>
          )}
          <dl className="pp-greeting__stats">
            {stats.map((stat) => (
              <div key={stat.label} className="pp-greeting__stat">
                <dt>{stat.label}</dt>
                <dd>{stat.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}
