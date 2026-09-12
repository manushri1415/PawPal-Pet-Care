import './OverlapBanner.css';
import { useQuery } from '@tanstack/react-query';
import { Alert } from '../../components/Alert';
import { getOverlaps } from '../../api/scheduler';

export function OverlapBanner() {
  const { data, isLoading } = useQuery({
    queryKey: ['tasks', 'overlaps'],
    queryFn: getOverlaps,
  });

  if (isLoading || !data || data.overlaps.length === 0) {
    return null;
  }

  return (
    <div className="pp-overlap-banner">
      <Alert tone="warning">
        <p className="pp-overlap-banner-heading">Scheduling overlaps detected</p>
        <ul className="pp-overlap-banner-list">
          {data.overlaps.map((overlap) => (
            <li key={overlap}>{overlap}</li>
          ))}
        </ul>
      </Alert>
    </div>
  );
}
