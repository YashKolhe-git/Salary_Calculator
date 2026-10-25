import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background";

const disabledState =
  "disabled:pointer-events-none disabled:opacity-55 disabled:shadow-none disabled:active:scale-100";

const iconStyles =
  "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 motion-safe:transition-[color,background-color,box-shadow,transform]";

const primaryFill = cn(
  "border border-transparent bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover active:bg-primary-active active:scale-[0.98]",
  focusRing,
  disabledState,
  iconStyles,
  "[&_svg]:text-primary-foreground",
);

const secondaryFill = cn(
  "border-2 border-border bg-card text-foreground shadow-sm hover:bg-accent hover:border-accent active:bg-accent/90 active:scale-[0.98]",
  focusRing,
  disabledState,
  iconStyles,
  "[&_svg]:text-primary",
);

const ghostFill = cn(
  "border border-transparent bg-transparent text-foreground hover:bg-accent active:bg-accent/90 active:scale-[0.98]",
  focusRing,
  disabledState,
  iconStyles,
  "[&_svg]:text-primary",
);

const linkFill = cn(
  "border border-transparent bg-transparent text-primary underline-offset-4 hover:underline hover:bg-transparent active:scale-100",
  focusRing,
  disabledState,
  iconStyles,
  "[&_svg]:text-primary",
);

const destructiveFill = cn(
  "border border-transparent bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90 active:bg-destructive/80 active:scale-[0.98]",
  focusRing,
  disabledState,
  iconStyles,
  "[&_svg]:text-destructive-foreground",
);

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold",
  {
    variants: {
      variant: {
        default: primaryFill,
        destructive: destructiveFill,
        outline: secondaryFill,
        secondary: secondaryFill,
        ghost: ghostFill,
        link: linkFill,
      },
      size: {
        default: "min-h-10 h-10 px-4 py-2",
        sm: "min-h-9 h-9 rounded-lg px-3 text-xs",
        lg: "min-h-11 h-11 rounded-lg px-8",
        xl: "min-h-12 h-12 rounded-lg px-5 text-base font-semibold [&_svg]:size-5",
        icon: "size-10 min-h-10 w-10 shrink-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
