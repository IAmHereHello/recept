import { createPortal } from 'react-dom'

const DIFF_LABELS = { easy: 'Makkelijk', medium: 'Gemiddeld', hard: 'Moeilijk' }

// A4 print version of a recipe. Rendered next to #root (via a portal) and
// hidden on screen; the @media print rules in index.css hide the app and show
// only this sheet, so window.print() prints just the recipe.
export function RecipePrintSheet({ recipe, timeEst }) {
  const mainSteps = (recipe.steps || []).filter(s => s.track !== 'meanwhile')
  const meanwhileSteps = (recipe.steps || []).filter(s => s.track === 'meanwhile')

  const meta = [
    timeEst && `${timeEst.measured ? '~' : ''}${timeEst.minutes} min`,
    recipe.prep_time && `${recipe.prep_time} min actief`,
    recipe.portions && `${recipe.portions} ${recipe.portions === 1 ? 'portie' : 'porties'}`,
    recipe.difficulty && DIFF_LABELS[recipe.difficulty],
    recipe.cuisine_type,
    recipe.is_vegan ? 'Vegan' : recipe.is_vegetarian ? 'Vegetarisch' : null,
  ].filter(Boolean)

  const printedOn = new Date().toLocaleDateString('nl-NL', { day: 'numeric', month: 'long', year: 'numeric' })

  return createPortal(
    <article className="print-sheet" data-testid="print-sheet">
      <header className="ps-header">
        <div className="ps-title-block">
          <h1 className="ps-title">{recipe.name}</h1>
          {meta.length > 0 && <p className="ps-meta">{meta.join('  ·  ')}</p>}
          {recipe.description && <p className="ps-description">{recipe.description}</p>}
        </div>
        {recipe.cover_photo && <img className="ps-photo" src={recipe.cover_photo} alt="" />}
      </header>

      <div className="ps-body">
        {recipe.ingredients?.length > 0 && (
          <section className="ps-ingredients">
            <h2 className="ps-heading">Ingrediënten</h2>
            <ul>
              {recipe.ingredients.map(ing => (
                <li key={ing.id ?? ing.name}>
                  <span className="ps-box" />
                  <span>
                    {ing.amount && <strong>{ing.amount}{ing.unit ? ` ${ing.unit}` : ''} </strong>}
                    {ing.name}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="ps-method">
          {mainSteps.length > 0 && (
            <section>
              <h2 className="ps-heading">Bereiding</h2>
              <ol className="ps-steps">
                {mainSteps.map((step, i) => (
                  <li key={i}>
                    <span className="ps-num">{i + 1}</span>
                    <p>
                      {step.description}
                      {step.wait_time_minutes && <em className="ps-wait"> ({step.wait_time_minutes} min wachten)</em>}
                    </p>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {meanwhileSteps.length > 0 && (
            <section className="ps-meanwhile">
              <h2 className="ps-heading">Ondertussen</h2>
              <ul>
                {meanwhileSteps.map((step, i) => <li key={i}>{step.description}</li>)}
              </ul>
            </section>
          )}
        </div>
      </div>

      <section className="ps-notes">
        <h2 className="ps-heading">Notities</h2>
        <div className="ps-lines" />
      </section>

      <footer className="ps-footer">
        <span>Uit het receptenboek van Rachel &amp; Michael</span>
        <span>{printedOn}</span>
      </footer>
    </article>,
    document.body
  )
}
