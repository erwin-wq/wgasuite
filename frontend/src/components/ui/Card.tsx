import { type ElementType, type HTMLAttributes, type ReactNode } from "react";

import { cx } from "./utils";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: "article" | "aside" | "div" | "section";
  padding?: "none" | "sm" | "md" | "lg";
  elevation?: "flat" | "raised";
  children: ReactNode;
}

export function Card({
  as = "section",
  padding = "md",
  elevation = "flat",
  className,
  children,
  ...props
}: CardProps) {
  const Element: ElementType = as;
  return (
    <Element
      {...props}
      className={cx("ui-card", `ui-card--padding-${padding}`, `ui-card--${elevation}`, className)}
    >
      {children}
    </Element>
  );
}
