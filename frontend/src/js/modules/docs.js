import { copyText } from "./clipboard.js";

export function initDocsEnhancements(root = document) {
  root.querySelectorAll("[data-docs-page]").forEach((page) => {
    addCodeCopyButtons(page);
    buildTableOfContents(page);
  });
}

function addCodeCopyButtons(page) {
  page.querySelectorAll("pre").forEach((block) => {
    if (block.dataset.copyEnhanced === "true") {
      return;
    }

    const code = block.querySelector("code");
    if (!code) {
      return;
    }

    block.dataset.copyEnhanced = "true";
    const wrapper = document.createElement("div");
    wrapper.className = "group relative my-6";
    block.parentNode.insertBefore(wrapper, block);
    wrapper.appendChild(block);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "absolute right-3 top-3 rounded-lg border border-gray-700 bg-gray-900/90 px-2.5 py-1 text-xs font-semibold text-gray-200 opacity-0 shadow-sm transition hover:bg-gray-800 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-500 group-hover:opacity-100";
    button.textContent = "Copy";
    button.addEventListener("click", () => copyCode(code.textContent, button));
    wrapper.appendChild(button);
  });
}

async function copyCode(text, button) {
  const copied = await copyText(text);
  const original = button.dataset.originalLabel || button.textContent;
  button.dataset.originalLabel = original;
  button.textContent = copied ? "Copied" : "Copy failed";
  window.clearTimeout(Number(button.dataset.resetTimer));
  button.dataset.resetTimer = window.setTimeout(() => {
    button.textContent = original;
  }, 1600);
}

function buildTableOfContents(page) {
  const content = page.querySelector("[data-toc-content]");
  const list = page.querySelector("[data-toc-list]");
  const sidebar = page.querySelector("[data-toc-sidebar]");

  if (!content || !list) {
    return;
  }

  const headings = Array.from(content.querySelectorAll("h2"));
  if (headings.length === 0) {
    if (sidebar) {
      sidebar.hidden = true;
    }
    return;
  }

  list.replaceChildren();
  headings.forEach((heading) => {
    const headingText = heading.textContent.trim();
    const headingId = heading.id || slugify(headingText);
    heading.id = headingId;

    const listItem = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#${headingId}`;
    link.textContent = headingText;
    link.dataset.tocLink = "";
    link.dataset.section = headingId;
    link.className = "block border-l-2 border-gray-200 py-1.5 pl-3 text-sm text-gray-600 transition-colors hover:border-gray-400 hover:text-gray-900 dark:border-gray-700 dark:text-gray-300 dark:hover:border-gray-500 dark:hover:text-gray-100";
    link.addEventListener("click", (event) => {
      event.preventDefault();
      scrollToSection(headingId);
      updateActiveLink(page, headingId);
    });

    listItem.appendChild(link);
    list.appendChild(listItem);
  });

  const highlightCurrentSection = () => {
    const scrollPosition = window.scrollY + 100;
    const current = headings.reduce((currentId, heading) => {
      if (scrollPosition >= heading.offsetTop) {
        return heading.id;
      }
      return currentId;
    }, "");

    if (current) {
      updateActiveLink(page, current);
    }
  };

  highlightCurrentSection();
  window.addEventListener("scroll", highlightCurrentSection, { passive: true });
}

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

function scrollToSection(sectionId) {
  const section = document.getElementById(sectionId);
  if (!section) {
    return;
  }

  const offsetPosition = section.getBoundingClientRect().top + window.pageYOffset - 80;
  window.scrollTo({ top: offsetPosition, behavior: "smooth" });
}

function updateActiveLink(page, activeSectionId) {
  page.querySelectorAll("[data-toc-link]").forEach((link) => {
    const isActive = link.dataset.section === activeSectionId;
    link.classList.toggle("border-green-600", isActive);
    link.classList.toggle("text-green-600", isActive);
    link.classList.toggle("font-medium", isActive);
    link.classList.toggle("border-gray-200", !isActive);
    link.classList.toggle("text-gray-600", !isActive);
  });
}
