import { getRequestConfig } from "next-intl/server";

/**
 * next-intl request configuration (P0-082, spec section 5 "i18n: next-intl,
 * prepared, English first"). v1 ships one locale with no URL prefix; adding
 * a second locale later is a matter of resolving `locale` from the request
 * instead of hard-coding it, not a rewrite of this module or of any screen.
 */
export default getRequestConfig(async () => {
  const locale = "en";

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
