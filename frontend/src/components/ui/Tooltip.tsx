import { cloneElement, type ReactElement, type ReactNode, useId } from "react";

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement<{ "aria-describedby"?: string }>;
  placement?: "top" | "bottom";
}

export function Tooltip({ content, children, placement = "top" }: TooltipProps) {
  const tooltipId = useId();
  const describedBy = [children.props["aria-describedby"], tooltipId].filter(Boolean).join(" ");
  return (
    <span className={`ui-tooltip ui-tooltip--${placement}`}>
      {cloneElement(children, { "aria-describedby": describedBy })}
      <span id={tooltipId} className="ui-tooltip__content" role="tooltip">
        {content}
      </span>
    </span>
  );
}
