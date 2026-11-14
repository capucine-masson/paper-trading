export function Loading() {
  return <p className="feedback">Loading dashboard...</p>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <p className="feedback feedback-error" role="alert">
      {message}
    </p>
  );
}

export function Empty({ message }: { message: string }) {
  return <p className="feedback">{message}</p>;
}
