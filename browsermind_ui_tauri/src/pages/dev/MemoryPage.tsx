import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tag,
} from "@/components/ui";
import { adapter } from "@/lib/adapters";
import { formatRelative } from "@/lib/utils";
import type { MemoryEntry, MemoryType } from "@/types";

const TYPES: MemoryType[] = ["episodic", "semantic", "procedural"];

export default function MemoryPage() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold tracking-tight">Memory</h1>
        <p className="text-xs text-text-muted">
          Episodic events, semantic knowledge, and procedural skills.
        </p>
      </header>

      <Tabs defaultValue="episodic">
        <TabsList>
          {TYPES.map((t) => (
            <TabsTrigger key={t} value={t} className="capitalize">
              {t}
            </TabsTrigger>
          ))}
        </TabsList>

        {TYPES.map((t) => (
          <TabsContent key={t} value={t} className="mt-4">
            <MemorySection type={t} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

function MemorySection({ type }: { type: MemoryType }) {
  const [open, setOpen] = useState<MemoryEntry | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["memory", type],
    queryFn: () => adapter.memory.list(type),
  });

  return (
    <>
      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list">List</TabsTrigger>
          <TabsTrigger value="graph">Graph</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="mt-3">
          <div className="rounded-lg border border-border-default bg-bg-panel overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead className="text-right">Relations</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading
                  ? Array.from({ length: 4 }).map((_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={4}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  : (data ?? []).map((m) => (
                      <TableRow
                        key={m.id}
                        className="cursor-pointer"
                        onClick={() => setOpen(m)}
                      >
                        <TableCell className="font-medium">{m.title}</TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {(m.tags ?? []).map((tg) => (
                              <Tag key={tg} variant="neutral">{tg}</Tag>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {m.relatedEntities.length}
                        </TableCell>
                        <TableCell className="text-xs text-text-muted">
                          {formatRelative(m.createdAt)}
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="graph" className="mt-3">
          <div className="grid grid-cols-2 gap-3">
            {(data ?? []).slice(0, 6).map((m) => (
              <Card key={m.id}>
                <CardHeader>
                  <CardTitle>{m.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {m.relatedEntities.map((r) => (
                      <span
                        key={r.id}
                        className="inline-flex items-center gap-1 rounded-md border border-border-default bg-bg-elevated px-2 h-6 text-[11px] text-text-muted"
                      >
                        <span className="text-text-subtle">{r.type}</span>
                        <span>{r.label}</span>
                      </span>
                    ))}
                    {m.relatedEntities.length === 0 && (
                      <span className="text-[11px] text-text-subtle">
                        no relations
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="timeline" className="mt-3">
          <Card>
            <CardContent className="p-0">
              <ul>
                {(data ?? [])
                  .slice()
                  .sort(
                    (a, b) =>
                      new Date(b.createdAt).getTime() -
                      new Date(a.createdAt).getTime(),
                  )
                  .map((m) => (
                    <li
                      key={m.id}
                      className="flex items-center gap-3 px-4 py-2 border-t first:border-t-0 border-border-default"
                    >
                      <span className="font-mono text-[11px] text-text-subtle w-24">
                        {formatRelative(m.createdAt)}
                      </span>
                      <span className="flex-1 text-sm">{m.title}</span>
                      <Tag variant="neutral">{m.type}</Tag>
                    </li>
                  ))}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Sheet open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent side="right" className="w-[420px]">
          {open && (
            <>
              <SheetHeader>
                <SheetTitle>{open.title}</SheetTitle>
              </SheetHeader>
              <div className="mt-4 space-y-3 text-sm">
                <Tag variant="neutral">{open.type}</Tag>
                <div className="text-text-muted whitespace-pre-wrap">
                  {open.content}
                </div>
                {open.relatedEntities.length > 0 && (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-text-subtle mb-1">
                      Related
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {open.relatedEntities.map((r) => (
                        <Tag key={r.id} variant="neutral">{r.type}: {r.label}</Tag>
                      ))}
                    </div>
                  </div>
                )}
                <div className="text-[11px] text-text-subtle">
                  Created {formatRelative(open.createdAt)} • <span className="font-mono">{open.id}</span>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
