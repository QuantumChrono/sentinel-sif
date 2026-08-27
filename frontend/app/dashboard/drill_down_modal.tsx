"use client";

/**
 * Drill-down modal: shows reports for a selected site or activity from the density ranking.
 * 
 * LOADING STATES as discriminated unions: loading | loaded | failed.
 * Never throws, never leaves UI in impossible state.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { listReports, type ApiError, type ReportDetail } from "@/lib/api_client";
import { ReportResult } from "@/app/report_result";

type Load =
  | { name: "loading" }
  | { name: "loaded"; reports: ReportDetail[] }
  | { name: "failed"; error: ApiError };

export function DrillDownModal({
  groupType,
  groupName,
  groupId,
  onClose,
}: {
  groupType: "site" | "activity";
  groupName: string;
  groupId: string | null;
  onClose: () => void;
}) {
  const [load, setLoad] = useState<Load>({ name: "loading" });

  useEffect(() => {
    (async () => {
      try {
        // Fetch reports filtered by site_id or activity
        const filters =
          groupType === "site" && groupId
            ? { site_id: groupId, limit: 200 }
            : groupType === "activity"
              ? { activity: groupName, limit: 200 }
              : {};

        const result = await listReports(filters);
        if (!result.ok) {
          setLoad({ name: "failed", error: result.error });
        } else {
          setLoad({ name: "loaded", reports: result.data });
        }
      } catch (error) {
        setLoad({
          name: "failed",
          error: {
            kind: "server",
            message: "An unexpected error occurred",
            status: null,
          },
        });
      }
    })();
  }, [groupType, groupName, groupId]);

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/50 sm:items-center sm:justify-center">
      <div className="h-screen w-full overflow-y-auto bg-white sm:h-auto sm:max-h-[90vh] sm:max-w-2xl sm:rounded-lg">
        <div className="sticky top-0 border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">
              {groupType === "site" ? "Site" : "Activity"}: {groupName}
            </h2>
            <p className="text-sm text-slate-600">Reports in this group</p>
          </div>
          <button
            onClick={onClose}
            className="rounded hover:bg-slate-100 p-2 text-slate-600 hover:text-slate-900"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-6">
          {load.name === "loading" && (
            <p className="text-sm text-slate-600">Loading reports…</p>
          )}

          {load.name === "failed" && (
            <div role="alert" className="space-y-2 rounded border border-rose-300 bg-rose-50 p-4">
              <h3 className="font-semibold text-rose-900">Could not load reports</h3>
              <p className="text-sm text-rose-900">{load.error.message}</p>
            </div>
          )}

          {load.name === "loaded" && (
            <>
              <p className="mb-4 text-sm text-slate-600">
                {load.reports.length} report{load.reports.length === 1 ? "" : "s"}
              </p>
              {load.reports.length === 0 ? (
                <div className="rounded border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm text-slate-600">No reports found.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {load.reports.map((report) => (
                    <div
                      key={report.id}
                      className="rounded border border-slate-200 bg-white p-4"
                    >
                      <ReportResult report={report} />
                      <div className="mt-4 flex justify-end">
                        <Link
                          href={`/reports/${report.id}`}
                          className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
                        >
                          Open full report →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
