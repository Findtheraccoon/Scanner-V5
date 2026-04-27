import "./stub.css";

interface StubPageProps {
  title: string;
  description: string;
}

export function StubPage({ title, description }: StubPageProps) {
  return (
    <main className="stub">
      <div className="stub__panel">
        <span className="stub__label">próximamente</span>
        <h1 className="stub__title">{title}</h1>
        <p className="stub__desc">{description}</p>
        <span className="stub__hint">
          Este shell se reemplaza cuando llegue el hi-fi de la pestaña.
        </span>
      </div>
    </main>
  );
}
