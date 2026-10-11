// The help centre this agent answers from, and the order system it can look things up in.

export const ARTICLES: Record<string, string> = {
  refunds:
    "Annual plans can be refunded in full within 30 days of purchase. After 30 days the refund is prorated by unused full months. Monthly plans are not refunded, but they can be cancelled at any time and stay active until the end of the paid month. Refunds go back to the original payment method within 5 to 7 business days.",
  seats:
    "Seats are billed per active member. Adding a seat mid-cycle is charged pro rata for the rest of the cycle. Removing a seat takes effect at the next renewal; no credit is given for the current cycle. The Team plan includes 5 seats and the Business plan includes 20.",
  export:
    "Workspace owners can export all data from Settings, Data, Export. The export is a zip of JSON files and attachments. Exports of more than 10 GB are prepared in the background and a download link is emailed within 24 hours. Links expire after 7 days.",
  sso:
    "Single sign-on with SAML is available on the Business plan. Supported identity providers are Okta, Microsoft Entra ID and Google Workspace. SCIM provisioning is included. Enforcing SSO signs out every member and requires them to sign in through the identity provider.",
  invoices:
    "Invoices are issued on the first day of each billing cycle and emailed to every billing contact. A tax id or a purchase order number can be added in Settings, Billing, Invoice details and appears on invoices from then on; past invoices can be reissued once on request. Payment by bank transfer is offered on annual Business plans above 50 seats, with 30 day terms.",
  trial:
    "Every new workspace starts with a 14 day trial of the Business plan and no card is needed. At the end of the trial the workspace moves to the Free plan unless a paid plan is chosen. Trial data is kept. A trial can be extended once by 7 days on request to support.",
  api:
    "The public API allows 600 requests per minute per workspace on the Team plan and 3,000 on the Business plan. Requests over the limit receive a 429 response with a Retry-After header. Webhooks are retried for 24 hours with exponential backoff, and an endpoint that fails for 3 days in a row is disabled and the owner is emailed.",
  retention:
    "Deleted items stay in the trash for 30 days and can be restored by any admin. After 30 days they are removed permanently, and from backups within a further 35 days. Audit logs are kept for 90 days on the Team plan and 1 year on the Business plan and can be exported as CSV.",
  ownership:
    "A workspace has exactly one owner. The owner can transfer ownership to any admin from Settings, Members; the transfer takes effect when the new owner accepts by email within 7 days. If the owner has left the company, a transfer can be requested by an admin with proof of authority and is completed after a 5 business day waiting period.",
  permissions:
    "There are four roles. Owners manage billing and can delete the workspace. Admins manage members, groups and integrations but cannot see invoices. Members can create and edit content in the spaces they belong to. Guests are free, can be invited to at most 3 spaces, and cannot see the member directory. A custom role can be defined on the Business plan from Settings, Roles.",
  integrations:
    "Integrations are installed per workspace by an admin. The Slack integration posts updates to a channel and can create items from a message. The GitHub integration links pull requests to items and closes them on merge. Each integration asks only for the scopes it lists on its install screen, and removing it revokes its token within 1 hour.",
  mobile:
    "The mobile apps need iOS 17 or Android 12 and later. Offline edits are stored on the device and synced when a connection returns; if the same field was changed elsewhere, the newer change wins and the older one is kept in the item's history. Push notifications can be limited to mentions from the app's settings.",
  security:
    "Data is encrypted in transit with TLS 1.3 and at rest with AES-256. Two-factor authentication can be required for every member by an admin. Sessions end after 30 days without use, or after 12 hours when the admin turns on strict sessions. A SOC 2 Type II report is available to Business plan customers under a non-disclosure agreement.",
  downgrade:
    "A workspace can move to a lower plan at any time; the change takes effect at the next renewal and no refund is given for the remaining cycle. Features of the higher plan stay available until then. If the lower plan allows fewer seats than are in use, the owner must remove members before the renewal date or the downgrade is cancelled.",
  outage:
    "Status is published at status.example.com. Incidents that last longer than 30 minutes earn a service credit of 10 percent of the monthly fee on the Business plan, applied to the next invoice on request within 30 days.",
};

export const GUIDE = Object.entries(ARTICLES)
  .map(([name, text]) => `## ${name}\n${text}`)
  .join("\n\n");

const ORDERS: Record<string, { plan: string; billing: string; purchased: string; seats: number }> = {
  "A-1042": { plan: "Business", billing: "annual", purchased: "2026-09-20", seats: 24 },
  "A-2210": { plan: "Team", billing: "monthly", purchased: "2026-10-01", seats: 5 },
  "A-3377": { plan: "Business", billing: "annual", purchased: "2026-03-02", seats: 40 },
};

export function searchHelp(query: string): string {
  const q = query.toLowerCase();
  const hits = Object.entries(ARTICLES).filter(([name, text]) => q.includes(name) || text.toLowerCase().split(/\W+/).some((w) => w.length > 5 && q.includes(w)));
  const chosen = hits.length ? hits : Object.entries(ARTICLES).slice(0, 2);
  return chosen.map(([name, text]) => `[${name}] ${text}`).join("\n");
}

export function lookupOrder(id: string): string {
  const order = ORDERS[id.trim().toUpperCase()];
  return order ? JSON.stringify(order) : `no order with id ${id}`;
}
