import { type ReactNode } from "react";

import { cx } from "./utils";

export interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumbs?: readonly string[];
  eyebrow?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  description,
  breadcrumbs = [],
  eyebrow,
  actions,
  className
}: PageHeaderProps) {
  return (
    <header className={cx("ui-page-header", className)}>
      <div className="ui-page-header__content">
        {breadcrumbs.length > 0 ? (
          <nav className="ui-breadcrumbs" aria-label="Breadcrumb">
            {breadcrumbs.map((item, index) => (
              <span key={`${item}:${index}`}>
                {index > 0 ? <span className="ui-breadcrumbs__separator" aria-hidden="true">/</span> : null}
                <span aria-current={index === breadcrumbs.length - 1 ? "page" : undefined}>{item}</span>
              </span>
            ))}
          </nav>
        ) : null}
        {eyebrow ? <span className="ui-page-header__eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="ui-page-header__actions">{actions}</div> : null}
    </header>
  );
}
