// Source-owned shadcn/ui Radix Tabs composition, styled with Job Pilot tokens.
// Adapted from shadcn/ui (MIT, Copyright (c) 2023 shadcn). See THIRD_PARTY_LICENSES.md.
import * as Primitive from '@radix-ui/react-tabs';
import type { ComponentProps } from 'react';
export const Tabs = Primitive.Root;
export function TabsList({className = '', children, ...props}: ComponentProps<typeof Primitive.List>) {
  return <Primitive.List className={`tabs-list ${className}`} {...props} asChild><CspPanel>{children}</CspPanel></Primitive.List>;
}
export function TabsTrigger({className = '', ...props}: ComponentProps<typeof Primitive.Trigger>) {
  return <Primitive.Trigger className={`tabs-trigger ${className}`} {...props} />;
}
function CspPanel({style, ...props}: ComponentProps<'div'>) {
  // Radix's initial animationDuration style is unnecessary with static CSS.
  // Strip it before DOM rendering; preserve Radix IDs, ARIA and focus behavior.
  void style;
  return <div {...props} />;
}
export function TabsContent({children, ...props}: ComponentProps<typeof Primitive.Content>) {
  return <Primitive.Content {...props} asChild><CspPanel>{children}</CspPanel></Primitive.Content>;
}
